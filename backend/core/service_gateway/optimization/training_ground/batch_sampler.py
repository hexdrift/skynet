"""Curriculum-aware minibatch sampler for GEPA.

Weights examples toward those where candidates are simultaneously failing
AND improving — a discrete-optimization analogue of Pedagogical RL's
spike-aware learnability score. The signal is computed from
``state.full_program_trace`` (each iteration records its
``subsample_ids`` + ``subsample_scores``) without hooking the adapter.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

from gepa.core.data_loader import DataLoader
from gepa.core.state import GEPAState
from gepa.strategies.batch_sampler import BatchSampler

_BASE_WEIGHT = 0.05
_DEFICIT_GAIN_FLOOR = 0.10
_RECENT_WINDOW = 6
_FRESH_SAMPLES_FRAC = 0.25


class PedagogicalBatchSampler(BatchSampler):
    """Pull-toward-learnable-examples sampler.

    weight(tid) = ``_BASE_WEIGHT`` + (1 - best_score(tid)) *
    (``_DEFICIT_GAIN_FLOOR`` + recent_gain(tid))

    A fraction (``_FRESH_SAMPLES_FRAC``) of every minibatch is reserved
    for the least-frequently-sampled ids so brand-new candidates can
    surface evidence for previously-unseen turns before they are pruned.

    Args:
        batch_size: Minibatch size to return.
        seed: Optional RNG seed for reproducible curriculum.
    """

    def __init__(self, batch_size: int, *, seed: int = 0) -> None:
        """Initialise the sampler with a minibatch size and RNG seed.

        Raises:
            ValueError: When ``batch_size`` is not positive.
        """
        if batch_size <= 0:
            raise ValueError("PedagogicalBatchSampler requires batch_size > 0")
        self._batch_size = batch_size
        self._rng = random.Random(seed)
        self._sample_counts: dict[Any, int] = {}
        self._best_score: dict[Any, float] = {}

    def next_minibatch_ids(
        self,
        loader: DataLoader[Any, Any],
        state: GEPAState[Any, Any],
    ) -> list[Any]:
        """Choose the next minibatch of training ids.

        Returns:
            A list of length ``batch_size`` drawn without replacement from
            ``loader.all_ids()``.
        """
        all_ids: list[Any] = list(loader.all_ids())
        if not all_ids:
            raise ValueError("PedagogicalBatchSampler: empty trainset")
        if len(all_ids) <= self._batch_size:
            self._bump_counts(all_ids)
            return all_ids

        score_history = self._build_score_history(state)
        weights = [self._weight_for(tid, score_history) for tid in all_ids]

        n_fresh = max(1, round(self._batch_size * _FRESH_SAMPLES_FRAC))
        n_curriculum = self._batch_size - n_fresh

        fresh = self._sample_least_seen(all_ids, n_fresh)
        remaining_ids = [tid for tid in all_ids if tid not in fresh]
        remaining_weights = [weights[i] for i, tid in enumerate(all_ids) if tid not in fresh]

        curriculum = self._weighted_sample_without_replacement(
            remaining_ids, remaining_weights, n_curriculum
        )
        chosen = fresh + curriculum
        self._bump_counts(chosen)
        return chosen

    def _bump_counts(self, ids: Sequence[Any]) -> None:
        """Track how often each id has been sampled (used by fresh-sample carve-out)."""
        for tid in ids:
            self._sample_counts[tid] = self._sample_counts.get(tid, 0) + 1

    def _sample_least_seen(self, all_ids: Sequence[Any], n: int) -> list[Any]:
        """Pick ``n`` ids with the lowest sample count, ties broken by RNG."""
        ranked = sorted(
            all_ids,
            key=lambda tid: (self._sample_counts.get(tid, 0), self._rng.random()),
        )
        return ranked[:n]

    def _build_score_history(
        self, state: GEPAState[Any, Any]
    ) -> dict[Any, list[float]]:
        """Reconstruct per-id windowed score history from the GEPA trace.

        ``state.full_program_trace`` is a list of dicts, each with
        ``subsample_ids`` and ``subsample_scores``. The order is iteration
        order; we keep only the most recent ``_RECENT_WINDOW`` observations
        per id so ``_recent_gain`` reacts to improvement, not ancient noise.

        Side effect: the all-time ``_best_score`` per id is updated here
        (max-merged across the full trace) so ``_weight_for`` can read it
        directly. Keeping it separate from the windowed list lets the
        deficit term ``(1 - best)`` stay anchored to an id's true ceiling
        even after the curriculum spends 6 iterations on it.
        """
        history: dict[Any, list[float]] = {}
        trace = getattr(state, "full_program_trace", None) or []
        for record in trace:
            if not isinstance(record, dict):
                continue
            ids = record.get("subsample_ids") or []
            scores = record.get("subsample_scores") or []
            for tid, score in zip(ids, scores, strict=False):
                value = float(score)
                bucket = history.setdefault(tid, [])
                bucket.append(value)
                if len(bucket) > _RECENT_WINDOW:
                    del bucket[0 : len(bucket) - _RECENT_WINDOW]
                prior_best = self._best_score.get(tid)
                if prior_best is None or value > prior_best:
                    self._best_score[tid] = value
        return history

    def _weight_for(self, tid: Any, history: dict[Any, list[float]]) -> float:
        """Compute the curriculum weight for one id."""
        observations = history.get(tid) or []
        if not observations:
            return _BASE_WEIGHT + _DEFICIT_GAIN_FLOOR
        best = self._best_score.get(tid, max(observations))
        recent_gain = self._recent_gain(observations)
        return _BASE_WEIGHT + (1.0 - best) * (_DEFICIT_GAIN_FLOOR + recent_gain)

    @staticmethod
    def _recent_gain(observations: Sequence[float]) -> float:
        """Mean delta between consecutive recent observations, clipped to [0, 1]."""
        if len(observations) < 2:
            return 0.0
        deltas = [
            observations[i] - observations[i - 1] for i in range(1, len(observations))
        ]
        avg = sum(deltas) / len(deltas)
        return max(0.0, min(1.0, avg))

    def _weighted_sample_without_replacement(
        self,
        candidates: Sequence[Any],
        weights: Sequence[float],
        k: int,
    ) -> list[Any]:
        """Draw ``k`` distinct items by reservoir-style weighted sampling.

        Uses the Efraimidis-Spirakis trick: u = rng.random() ** (1/w)
        ranks each item; the top-k by u are the sample. Faster than rejection
        sampling at small k and respects 0-weight items (excluded). When all
        weights are zero, fall back to uniform.
        """
        if k <= 0 or not candidates:
            return []
        positive_pool = [
            (tid, w) for tid, w in zip(candidates, weights, strict=False) if w > 0
        ]
        if not positive_pool:
            return self._rng.sample(list(candidates), min(k, len(candidates)))
        keys: list[tuple[float, Any]] = []
        for tid, w in positive_pool:
            u = self._rng.random() or 1e-12
            key = u ** (1.0 / w)
            keys.append((key, tid))
        keys.sort(key=lambda kv: kv[0], reverse=True)
        return [tid for _, tid in keys[:k]]


__all__ = ["PedagogicalBatchSampler"]
