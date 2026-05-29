"""ECHO-style observation-grounding reward for GEPA, scored 1:1 with serving.

Implements ECHO's objective ("Terminal Agents Learn World Models for Free",
arXiv 2605.24517) as a GEPA reward: the mean per-token log-likelihood the
frozen model assigns to the recorded environment observations (tool results),
teacher-forced in the EXACT context the served ``ReActV2`` program produces.
ECHO adds this at weight 0.05 on top of a GRPO task reward; we expose the raw
quantity (the negative of ECHO's ``L_Env`` cross-entropy) so it can drive a
grounding-only GEPA run or serve as one dimension of the vector reward.

Validated 1:1 recipe (see ``training_ground_SPEC.md`` §6):

    candidate's real DSPy ReActV2 messages
      -> apply_chat_template(msgs, tools, add_generation_prompt=False)   [MiniMax M2.7]
      -> strip the leading ']~!b[' BOS   (Fireworks /completions re-adds its
         own; stripping makes the token stream byte-identical to /chat — proven
         by exact prompt-token-count parity across cases)
      -> /completions echo -> per-token logprobs
      -> sum over the <response> observation spans / token count = reward.

The candidate prompt enters through the system slot + tool descriptions of the
rendered messages, so optimizing the prompt moves how surprised the model is by
the recorded environment responses — better grounding scores higher.

``transformers`` is an optional, optimizer-only dependency (the ``training``
extra). The serving runtime never imports this module.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

try:
    import httpx
except ImportError:  # optimizer-only optional dependency (the 'training' extra)
    httpx = None

try:
    from transformers import AutoTokenizer
except ImportError:  # optimizer-only optional dependency
    AutoTokenizer = None

FIREWORKS_COMPLETIONS_URL = "https://api.fireworks.ai/inference/v1/completions"
DEFAULT_HF_REPO = "MiniMaxAI/MiniMax-M2.7"

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
"""Browser-like UA. Fireworks sits behind Cloudflare, which 1010-blocks the
default ``Python-urllib`` signature; this header clears the edge."""


@dataclass(frozen=True)
class ScoredPrompt:
    """Per-token echo scoring of one prompt string.

    Args:
        tokens: The prompt tokens as the model tokenized them.
        logprobs: Per-token log-probabilities; the first is typically ``None``.
        offsets: Character offset of each token's start within the prompt.
    """

    tokens: tuple[str, ...]
    logprobs: tuple[float | None, ...]
    offsets: tuple[int, ...]


class PromptScorer(Protocol):
    """Maps a prompt string to its per-token echo scoring."""

    def __call__(self, prompt: str) -> ScoredPrompt:
        """Return the per-token logprobs + offsets for ``prompt``."""
        ...


class ChatTemplate(Protocol):
    """Renders a messages list into the served token string."""

    def render(
        self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None
    ) -> str:
        """Return the chat-template-applied prompt string."""
        ...


def _offsets_from_tokens(tokens: Sequence[str]) -> tuple[int, ...]:
    """Reconstruct each token's start char-offset by accumulating token lengths.

    Avoids trusting the API's optional ``text_offset`` field: BPE token strings
    concatenate back to the prompt, so cumulative lengths give exact offsets.
    """
    offsets: list[int] = []
    pos = 0
    for token in tokens:
        offsets.append(pos)
        pos += len(token)
    return tuple(offsets)


def find_observation_spans(
    templated: str, observation_texts: Sequence[str]
) -> list[tuple[int, int]]:
    """Locate each recorded observation's char span inside the templated prompt.

    Observations are matched in order, advancing a cursor so repeated results
    map to successive occurrences rather than re-matching the first. A text the
    template altered (not found verbatim) is skipped — it contributes no
    grounding signal rather than corrupting an unrelated span.

    Args:
        templated: The chat-template-applied prompt.
        observation_texts: Recorded tool-result strings, in trajectory order.

    Returns:
        ``(start, end)`` char spans, one per located observation.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    for text in observation_texts:
        if not text:
            continue
        idx = templated.find(text, cursor)
        if idx < 0:
            idx = templated.find(text)
        if idx < 0:
            continue
        spans.append((idx, idx + len(text)))
        cursor = idx + len(text)
    return spans


def _tokens_in_spans(
    scored: ScoredPrompt, spans: Sequence[tuple[int, int]]
) -> list[float]:
    """Return the logprobs of tokens whose start offset falls inside a span."""
    selected: list[float] = []
    for offset, logprob in zip(scored.offsets, scored.logprobs, strict=False):
        if logprob is None:
            continue
        if any(start <= offset < end for start, end in spans):
            selected.append(logprob)
    return selected


def score_observation_spans(
    templated: str, spans: Sequence[tuple[int, int]], scorer: PromptScorer
) -> tuple[float, int]:
    """Score the observation tokens: ``(summed_logprob, n_tokens)``.

    Returns ``(0.0, 0)`` when ``spans`` is empty so the caller can treat a
    no-observation turn as carrying no ECHO signal.
    """
    if not spans:
        return 0.0, 0
    selected = _tokens_in_spans(scorer(templated), spans)
    return math.fsum(selected), len(selected)


def grounding_reward_from_templated(
    templated: str, observation_texts: Sequence[str], *, scorer: PromptScorer
) -> float | None:
    """Mean per-token observation log-likelihood for an already-templated prompt.

    Returns:
        ECHO's ``-L_Env`` (higher = better grounded), or ``None`` when no
        recorded observation could be located in ``templated``.
    """
    spans = find_observation_spans(templated, observation_texts)
    total, count = score_observation_spans(templated, spans, scorer)
    if count == 0:
        return None
    return total / count


def grounding_reward(
    messages: list[dict[str, Any]],
    observation_texts: Sequence[str],
    *,
    template: ChatTemplate,
    scorer: PromptScorer,
    tools: list[dict[str, Any]] | None = None,
) -> float | None:
    """Render the candidate's served messages, then score observation grounding.

    Args:
        messages: The candidate's real DSPy ReActV2 messages for the turn.
        observation_texts: Recorded tool-result strings, in trajectory order.
        template: Chat-template renderer (``MiniMaxChatTemplate`` in production).
        scorer: Per-token prompt scorer (``FireworksEchoScorer`` in production).
        tools: Tool schemas to pass to the chat template, if any.

    Returns:
        The mean observation log-likelihood, or ``None`` for a turn whose
        recorded observations are absent from the rendered prompt.
    """
    templated = template.render(messages, tools=tools)
    return grounding_reward_from_templated(templated, observation_texts, scorer=scorer)


def as_unit_interval(mean_log_likelihood: float) -> float:
    """Map a mean per-token log-likelihood to ``(0, 1]`` via ``exp``.

    The geometric-mean per-token probability — a bounded, monotonic transform
    for frontiers that prefer ``[0, 1]``. Monotonic, so it preserves the
    optimization order.
    """
    return math.exp(mean_log_likelihood)


class MiniMaxChatTemplate:
    """Applies MiniMax M2.7's chat template, matching Fireworks 1:1.

    Renders messages via ``apply_chat_template`` and strips the leading
    ``]~!b[`` BOS — Fireworks ``/completions`` re-adds its own BOS at
    tokenization, so stripping ours makes the token stream byte-identical to
    what ``/chat`` (the serving path) builds. Verified by exact prompt-token
    parity (``training_ground_SPEC.md`` §6).

    Args:
        repo: Hugging Face repo holding the tokenizer + chat template.
        trust_remote_code: Passed to ``from_pretrained`` (MiniMax's card
            prescribes it).
    """

    def __init__(
        self, *, repo: str = DEFAULT_HF_REPO, trust_remote_code: bool = True
    ) -> None:
        """Load the MiniMax tokenizer from ``repo`` (see class ``Args``).

        Raises:
            RuntimeError: When the optional ``transformers`` dependency is absent.
        """
        if AutoTokenizer is None:
            msg = "transformers is required for MiniMaxChatTemplate; install the 'training' extra."
            raise RuntimeError(msg)
        self._tokenizer = AutoTokenizer.from_pretrained(
            repo, trust_remote_code=trust_remote_code
        )

    def render(
        self, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None
    ) -> str:
        """Render ``messages`` to the served token string (BOS stripped).

        Note:
            Tool-call ``arguments`` must be dicts, not JSON strings — MiniMax's
            template iterates ``.items()`` to emit ``<parameter>`` tags.
        """
        text = self._tokenizer.apply_chat_template(
            messages, tools=tools, tokenize=False, add_generation_prompt=False
        )
        bos = self._tokenizer.bos_token
        if bos and text.startswith(bos):
            text = text[len(bos) :]
        return text


class FireworksEchoScorer:
    """``PromptScorer`` backed by the Fireworks ``echo`` completion endpoint.

    Sends ``echo=true, logprobs=1, max_tokens=1`` and returns the logprobs over
    the supplied prompt tokens, dropping the single generated token the API
    appends. Verified as the only MiniMax-serving path that returns
    supplied-prompt logprobs (``training_ground_SPEC.md`` §6). Offsets are
    reconstructed from token strings rather than the optional ``text_offset``.

    Args:
        api_key: Fireworks API key.
        model: Fireworks model path (e.g. ``accounts/fireworks/models/minimax-m2p7``).
        base_url: Completions endpoint URL.
        timeout_s: Per-request timeout in seconds.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = FIREWORKS_COMPLETIONS_URL,
        timeout_s: float = 60.0,
    ) -> None:
        """Store the Fireworks credentials and endpoint (see class ``Args``).

        Raises:
            RuntimeError: When the optional ``httpx`` dependency is absent.
        """
        if httpx is None:
            msg = "httpx is required for FireworksEchoScorer; install the 'training' extra."
            raise RuntimeError(msg)
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout_s = timeout_s

    def __call__(self, prompt: str) -> ScoredPrompt:
        """Score ``prompt`` via one echo completion call.

        Raises:
            httpx.HTTPError: when the request fails or returns a non-2xx status.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        body = {
            "model": self._model,
            "prompt": prompt,
            "max_tokens": 1,
            "echo": True,
            "logprobs": 1,
            "temperature": 0,
        }
        response = httpx.post(
            self._base_url, json=body, headers=headers, timeout=self._timeout_s
        )
        response.raise_for_status()
        logprobs = response.json()["choices"][0]["logprobs"]
        tokens = list(logprobs.get("tokens") or [])
        token_logprobs = list(logprobs.get("token_logprobs") or [])
        if tokens:
            tokens = tokens[:-1]
            token_logprobs = token_logprobs[:-1]
        return ScoredPrompt(
            tokens=tuple(tokens),
            logprobs=tuple(token_logprobs),
            offsets=_offsets_from_tokens(tokens),
        )


__all__ = [
    "ChatTemplate",
    "FireworksEchoScorer",
    "MiniMaxChatTemplate",
    "PromptScorer",
    "ScoredPrompt",
    "as_unit_interval",
    "find_observation_spans",
    "grounding_reward",
    "grounding_reward_from_templated",
    "score_observation_spans",
]
