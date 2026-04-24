"""Probe-only helpers: adaptive subsampling, structured progress, scaling-law fit.

The ``/models/probe`` endpoint runs a tiny optimizer pass on each catalog
model and collects per-step validation scores as a *trajectory*. We fit a
saturation curve to that trajectory and rank models by the fitted
*asymptote* — what the model would converge to under a full optimization
run — instead of by the probe's noisy final score.

Three pieces live here:

1. **Subsampling** — ``compute_eval_count`` scales the probe's eval subset
   with the dataset size, and ``stratified_split`` keeps rare classes
   represented in both train and eval.

2. **Structured progress** — ``GEPAProgressHook`` captures per-iteration
   scores through the GEPA callback API (no log-regex parsing). It feeds
   into a ``ProbeProgressTracker`` that emits ``model_trajectory`` NDJSON
   events with incrementally re-fit scaling-law predictions.

3. **Scaling-law fit** — ``fit_scaling_law`` fits EXPD3 + POW3 via scipy
   ``curve_fit`` (trust-region reflective) and returns an inverse-MSE
   weighted ensemble asymptote, with a best-observed fallback that
   surfaces as ``signal="observed"`` when the fit is unreliable.

Requires DSPy ~=3.0 (``BaseCallback.on_evaluate_end`` and GEPA
``StopperProtocol`` via ``gepa_kwargs``). Pin in ``pyproject.toml``.

References:
- Domhan et al. 2015, *Speeding Up Automatic Hyperparameter Optimization
  of Deep Neural Networks by Extrapolation of Learning Curves*
- Viering & Loog 2021, *The Shape of Learning Curves: a Review*
- Wistuba & Pedapati 2020, *Learning to Rank Learning Curves*
"""

from __future__ import annotations

import logging
import math
import queue
import random
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from ...models import ColumnMapping

logger = logging.getLogger(__name__)


def compute_eval_count(dataset_size: int, default: int = 4) -> int:
    """Pick an eval subsample size that scales with the full dataset.

    Clamp formula: ``clamp(4, round(log2(N) * 2), 16)``. Caps at 16 so the
    probe stays cheap (each full eval costs ``eval_count`` metric calls).
    Falls back to ``default`` when N is too small to take a log of.
    """
    if dataset_size <= 1:
        return default
    scaled = round(math.log2(dataset_size) * 2)
    return max(4, min(16, scaled))


def _detect_strata_column(
    dataset: list[dict[str, Any]],
    mapping: ColumnMapping,
    pool_size: int,
) -> str | None:
    """Return the first output column that looks like a class label."""
    for col in mapping.outputs.values():
        uniq: set[Any] = set()
        for row in dataset[:pool_size]:
            val = row.get(col)
            if val is None:
                continue
            try:
                uniq.add(val)
            except TypeError:
                uniq = set()
                break
        if 2 <= len(uniq) <= 10 and len(uniq) * 4 <= pool_size:
            return col
    return None


def stratified_split(
    examples: list[Any],
    dataset: list[dict[str, Any]],
    mapping: ColumnMapping,
    train_count: int,
    eval_count: int,
    rng: random.Random,
) -> tuple[list[Any], list[Any]]:
    """Split ``examples`` into train/eval subsets, stratified when possible."""
    pool_size = min(len(examples), len(dataset))
    strata_col = _detect_strata_column(dataset, mapping, pool_size)

    if strata_col is None:
        indices = list(range(pool_size))
        rng.shuffle(indices)
        need = train_count + eval_count
        picked = indices[:need]
        train_idx = picked[:train_count]
        eval_idx = picked[train_count:need]
        return [examples[i] for i in train_idx], [examples[i] for i in eval_idx]

    buckets: dict[Any, list[int]] = {}
    for idx in range(pool_size):
        key = dataset[idx].get(strata_col)
        buckets.setdefault(key, []).append(idx)
    for indices in buckets.values():
        rng.shuffle(indices)

    ordered: list[int] = []
    bucket_lists = [list(b) for b in buckets.values()]
    while any(bucket_lists):
        for bucket in bucket_lists:
            if bucket:
                ordered.append(bucket.pop(0))

    need = train_count + eval_count
    picked = ordered[:need]
    train_idx = picked[:train_count]
    eval_idx = picked[train_count:need]
    return [examples[i] for i in train_idx], [examples[i] for i in eval_idx]


@dataclass(frozen=True)
class TrajectoryPoint:
    """One observed (step, score) pair from an optimizer run."""

    step: int
    score: float


@dataclass(frozen=True)
class ScalingLawFit:
    """Result of fitting a saturation curve to an optimizer trajectory.

    Signal states:

    - ``"strong"`` — EXPD3/POW3 curve fit converged with physically plausible
      parameters. The asymptote is an extrapolation we trust for ranking.
    - ``"observed"`` — curve fit unavailable or unreliable, but we have enough
      trajectory points that the best-observed value is a legitimate lower
      bound on the model's ceiling.
    - ``"weak"`` — insufficient data (0–1 trajectory points).
    """

    asymptote: float
    last_score: float
    method: str
    points: int
    signal: str
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "asymptote": None if math.isnan(self.asymptote) else round(self.asymptote, 4),
            "last_score": None if math.isnan(self.last_score) else round(self.last_score, 4),
            "method": self.method,
            "points": self.points,
            "signal": self.signal,
        }
        if self.message:
            payload["message"] = self.message
        return payload


# ── Structured progress callbacks ────────────────────────────────────


@dataclass
class ProbeProgressTracker:
    """Accumulates live trajectory points from structured callbacks.

    ``GEPAProgressHook`` pushes points here. The tracker emits
    ``model_trajectory`` NDJSON events to the shared queue, incrementally
    re-fitting the scaling law so the frontend sees the asymptote prediction
    converge in real time.
    """

    event_queue: queue.Queue
    position: int
    points: list[TrajectoryPoint] = field(default_factory=list)

    def record(self, step: int, score: float) -> None:
        if not math.isfinite(score):
            return
        point = TrajectoryPoint(step=step, score=score)
        self.points.append(point)
        try:
            fit = fit_scaling_law(self.points)
            scaling = fit.to_dict()
        except Exception:
            scaling = None
        self.event_queue.put({
            "event": "model_trajectory",
            "position": self.position,
            "point": {"step": step, "score": round(score, 4)},
            "scaling": scaling,
        })


class GEPAProgressHook:
    """Satisfies ``gepa.utils.stop_condition.StopperProtocol``.

    GEPA calls ``__call__(gepa_state)`` at every iteration. We read
    ``program_full_scores_val_set`` for newly discovered candidate scores
    and emit them as trajectory points.

    Scores are multiplied by 100 to match the 0–100 percentage scale
    used by ``dspy.Evaluate``.

    Always returns ``False`` (never triggers early stop).
    """

    def __init__(self, tracker: ProbeProgressTracker) -> None:
        self._tracker = tracker
        self._seen_count = 0

    def __call__(self, gepa_state: Any) -> bool:
        scores = getattr(gepa_state, "program_full_scores_val_set", None)
        if not scores:
            return False
        new_scores = scores[self._seen_count:]
        for i, raw_score in enumerate(new_scores):
            try:
                val = float(raw_score)
            except (TypeError, ValueError):
                continue
            step = self._seen_count + i
            self._tracker.record(step, val * 100.0)
        self._seen_count = len(scores)
        return False


# ── Scaling-law fit ──────────────────────────────────────────────────


def fit_scaling_law(trajectory: list[TrajectoryPoint]) -> ScalingLawFit:
    """Estimate an asymptote for an optimizer trajectory.

    Two-tier strategy:

    1. **Curve fit** (EXPD3 + POW3 ensemble, inverse-MSE weighted) on the
       *best-so-far* trace. The best-so-far envelope is monotonic by
       construction, which lets the fit ignore noisy bad trials.
    2. **Best-observed fallback** (``signal="observed"``) when the fit
       fails or we have too few points.
    """
    n_points = len(trajectory)
    if n_points == 0:
        return ScalingLawFit(
            asymptote=float("nan"),
            last_score=float("nan"),
            method="none",
            points=0,
            signal="weak",
            message="no trajectory points",
        )

    raw_scores = [p.score for p in trajectory]
    last_score = raw_scores[-1]
    bsf = np.maximum.accumulate(np.array(raw_scores, dtype=float))
    max_score = float(bsf[-1])

    if n_points == 1:
        return ScalingLawFit(
            asymptote=max_score,
            last_score=last_score,
            method="single_point",
            points=1,
            signal="weak",
            message="only 1 trajectory point; cannot extrapolate",
        )

    raw_range = float(max(raw_scores) - min(raw_scores))

    candidates: list[tuple[str, float, float]] = []
    if n_points >= 3 and raw_range >= 1e-6:
        xs = np.array([float(p.step) for p in trajectory], dtype=float)
        xs = xs - xs.min() + 1.0

        score_scale = max(abs(max_score), 1e-3)
        score_range_ref = max(raw_range, 0.05 * score_scale)
        c_lower = max_score - 1e-4
        c_upper = max_score + 3.0 * score_range_ref

        expd3 = _fit_expd3(xs, bsf, c_lower, c_upper)
        if expd3 is not None:
            candidates.append(("expd3", *expd3))
        pow3 = _fit_pow3(xs, bsf, c_lower, c_upper)
        if pow3 is not None:
            candidates.append(("pow3", *pow3))

        if candidates:
            asymptotes = np.array([c[1] for c in candidates])
            mses = np.array([max(c[2], 1e-9) for c in candidates])
            weights = 1.0 / mses
            weights = weights / weights.sum()
            ensemble = float(np.sum(asymptotes * weights))
            method = "+".join(c[0] for c in candidates)

            if max_score - 1e-3 <= ensemble <= c_upper + 1e-3:
                return ScalingLawFit(
                    asymptote=max(ensemble, max_score),
                    last_score=last_score,
                    method=method,
                    points=n_points,
                    signal="strong",
                )

    return ScalingLawFit(
        asymptote=max_score,
        last_score=last_score,
        method="best_observed" if not candidates else "best_observed_fallback",
        points=n_points,
        signal="observed",
        message="curve fit unavailable; best-observed score used as ceiling",
    )


def _fit_expd3(
    xs: np.ndarray,
    ys: np.ndarray,
    c_lower: float,
    c_upper: float,
) -> tuple[float, float] | None:
    """Fit ``y = c - (c - a) * exp(-b * n)``; return ``(asymptote, mse)``."""

    def expd3(n: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
        return c - (c - a) * np.exp(-b * n)

    y_min = float(ys.min())
    y_max = float(ys.max())
    p0 = [y_min, 0.5, min(c_upper, max(c_lower, y_max + 0.05))]
    bounds = (
        [y_min - 1.0, 1e-4, c_lower],
        [y_max + 1e-6, 10.0, c_upper],
    )
    try:
        popt, _ = curve_fit(
            expd3, xs, ys, p0=p0, bounds=bounds, method="trf", maxfev=2000
        )
    except (RuntimeError, ValueError) as exc:
        logger.debug("EXPD3 fit failed: %s", exc)
        return None

    residuals = ys - expd3(xs, *popt)
    mse = float(np.mean(residuals**2))
    asymptote = float(popt[2])
    if not math.isfinite(asymptote) or not math.isfinite(mse):
        return None
    return asymptote, mse


def _fit_pow3(
    xs: np.ndarray,
    ys: np.ndarray,
    c_lower: float,
    c_upper: float,
) -> tuple[float, float] | None:
    """Fit ``y = c - a * n^(-b)``; return ``(asymptote, mse)``."""

    def pow3(n: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
        return c - a * np.power(n, -b)

    y_max = float(ys.max())
    y_min = float(ys.min())
    a0 = max(c_lower - y_min, 0.1)
    p0 = [a0, 0.5, min(c_upper, max(c_lower, y_max + 0.05))]
    bounds = (
        [1e-4, 1e-3, c_lower],
        [10.0, 5.0, c_upper],
    )
    try:
        popt, _ = curve_fit(
            pow3, xs, ys, p0=p0, bounds=bounds, method="trf", maxfev=2000
        )
    except (RuntimeError, ValueError) as exc:
        logger.debug("POW3 fit failed: %s", exc)
        return None

    residuals = ys - pow3(xs, *popt)
    mse = float(np.mean(residuals**2))
    asymptote = float(popt[2])
    if not math.isfinite(asymptote) or not math.isfinite(mse):
        return None
    return asymptote, mse
