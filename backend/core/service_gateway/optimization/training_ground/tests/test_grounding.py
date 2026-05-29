"""Unit tests for the ECHO grounding reward's pure logic.

Covers span location, observation-token selection, and the mean-log-likelihood
math with a deterministic fake scorer + fake template — no network, no
``transformers``. The live pieces (``MiniMaxChatTemplate`` template fidelity and
``FireworksEchoScorer``) are validated against the real model by the §6 probes,
not here.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.service_gateway.optimization.training_ground import grounding
from core.service_gateway.optimization.training_ground.grounding import ScoredPrompt


class _CharScorer:
    """Deterministic fake scorer: one token per char, logprob(i) = -((i % 5) + 1).

    Offsets are the char indices, so the selected-token mean is computable
    independently of the code under test.
    """

    def __call__(self, prompt: str) -> ScoredPrompt:
        """Return a per-char scoring of ``prompt``."""
        return ScoredPrompt(
            tokens=tuple(prompt),
            logprobs=tuple(-((i % 5) + 1) for i in range(len(prompt))),
            offsets=tuple(range(len(prompt))),
        )


class _FixedTemplate:
    """Fake ``ChatTemplate`` returning a preset string regardless of input."""

    def __init__(self, text: str) -> None:
        self._text = text

    def render(
        self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None
    ) -> str:
        """Return the preset rendered string."""
        _ = (messages, tools)
        return self._text


def _expected_mean(text: str, obs: str) -> float:
    """Mean of the fake scorer's logprobs over ``obs``'s char span in ``text``."""
    start = text.index(obs)
    indices = range(start, start + len(obs))
    return sum(-((i % 5) + 1) for i in indices) / len(obs)


def test_offsets_from_tokens() -> None:
    """Offsets accumulate token string lengths."""
    assert grounding._offsets_from_tokens(["The", " cap", "ital"]) == (0, 3, 7)
    assert grounding._offsets_from_tokens([]) == ()


def test_find_spans_in_order() -> None:
    """Each observation maps to its char span."""
    assert grounding.find_observation_spans("aXXbYYc", ["XX", "YY"]) == [(1, 3), (4, 6)]


def test_find_spans_duplicates_advance_cursor() -> None:
    """A repeated observation maps to the next occurrence, not the first again."""
    assert grounding.find_observation_spans("XX---XX", ["XX", "XX"]) == [(0, 2), (5, 7)]


def test_find_spans_skips_missing() -> None:
    """An observation absent from the rendered text is skipped, not guessed."""
    assert grounding.find_observation_spans("hello world", ["zzz"]) == []


def test_grounding_reward_averages_observation_tokens() -> None:
    """The reward is the mean logprob over exactly the observation-span tokens."""
    templated = "PREFIXxxxxxSUFFIX"
    reward = grounding.grounding_reward_from_templated(
        templated, ["xxxxx"], scorer=_CharScorer()
    )
    assert reward == pytest.approx(_expected_mean(templated, "xxxxx"))


def test_grounding_reward_none_when_no_observation() -> None:
    """A turn whose observations aren't present scores ``None`` (no signal)."""
    assert (
        grounding.grounding_reward_from_templated("abc", ["zzz"], scorer=_CharScorer())
        is None
    )


def test_grounding_reward_renders_then_scores() -> None:
    """The messages pipeline renders via the template, then scores the spans."""
    templated = "ctx ]~b]tool\n<response>OBSDATA</response>[e~[ end"
    reward = grounding.grounding_reward(
        [{"role": "user", "content": "x"}],
        ["OBSDATA"],
        template=_FixedTemplate(templated),
        scorer=_CharScorer(),
    )
    assert reward == pytest.approx(_expected_mean(templated, "OBSDATA"))


def test_grounding_reward_multi_observation_pools_tokens() -> None:
    """Two observations are pooled into a single per-token mean."""
    templated = "AAA111BBB222CCC"
    reward = grounding.grounding_reward_from_templated(
        templated, ["111", "222"], scorer=_CharScorer()
    )
    s1, s2 = templated.index("111"), templated.index("222")
    idx = list(range(s1, s1 + 3)) + list(range(s2, s2 + 3))
    expected = sum(-((i % 5) + 1) for i in idx) / len(idx)
    assert reward == pytest.approx(expected)


def test_as_unit_interval() -> None:
    """exp maps mean-logprob into (0, 1], monotonic."""
    assert grounding.as_unit_interval(0.0) == pytest.approx(1.0)
    assert 0.0 < grounding.as_unit_interval(-1.0) < 1.0
    assert grounding.as_unit_interval(-0.5) > grounding.as_unit_interval(-1.0)
