"""OpenAI-compatible embedding API adapter for the explore-map projection.

The pipeline stores fixed-dimension pgvector embeddings, but the embedding
model itself is not bundled with the backend. Operators provide an internal
OpenAI-compatible embeddings endpoint and model id; this adapter sends text
to that endpoint, truncates the returned vector to the configured schema
dimension, and L2-normalizes it before storage.
"""

from __future__ import annotations

import logging
import math
import threading

import requests

from ...config import settings

logger = logging.getLogger(__name__)

_EMBEDDER_LOCK = threading.Lock()
_EMBEDDER_INSTANCE: _EmbeddingApiClient | None = None


class _EmbeddingApiClient:
    """Lazy singleton around an OpenAI-compatible embeddings endpoint."""

    def __init__(self) -> None:
        """Initialize immutable API settings from process configuration."""
        self._base_url = settings.embeddings_base_url.strip().rstrip("/")
        self._model = settings.embeddings_model.strip()
        self._dim = settings.embeddings_dim
        self._timeout = settings.default_timeout
        self._failed = False

    def available(self) -> bool:
        """Return whether the embedding API is configured for use."""
        if self._failed:
            return False
        if not self._base_url or not self._model:
            logger.warning(
                "Embedding API is not configured. Set EMBEDDINGS_BASE_URL and EMBEDDINGS_MODEL."
            )
            self._failed = True
            return False
        return True

    def encode(self, text: str) -> list[float] | None:
        """Return a truncated, L2-normalized embedding from the configured API.

        Args:
            text: The input string to embed.

        Returns:
            A normalized list of floats of length ``settings.embeddings_dim``,
            or ``None`` when the input is empty, the API is unavailable, the
            vector is too short, or the request/response is invalid.
        """
        if not text or not text.strip() or not self.available():
            return None
        try:
            raw = self._request_embedding(text)
            if len(raw) < self._dim:
                logger.warning(
                    "Embedding model %s returned %d dimensions; schema requires %d.",
                    self._model,
                    len(raw),
                    self._dim,
                )
                return None
            vector = [float(value) for value in raw[: self._dim]]
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0.0:
                return None
            return [value / norm for value in vector]
        except Exception as exc:
            logger.warning("Embedding API encode failed: %s", exc)
            return None

    def _request_embedding(self, text: str) -> list[float]:
        """Call the embedding API and return the first embedding vector.

        Args:
            text: The input string sent as the OpenAI-compatible ``input``.

        Returns:
            The first embedding vector returned by the API.

        Raises:
            TypeError: When the API response shape uses invalid types.
            ValueError: When the API response is missing required fields.
            requests.RequestException: When the HTTP request fails.
        """
        response = requests.post(
            f"{self._base_url}/embeddings",
            headers=self._headers(),
            json={"model": self._model, "input": text},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise ValueError("embedding response missing data[0]")
        first = data[0]
        if not isinstance(first, dict):
            raise TypeError("embedding response data[0] is not an object")
        embedding = first.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise ValueError("embedding response missing data[0].embedding")
        return embedding

    def _headers(self) -> dict[str, str]:
        """Build HTTP headers for the embedding request."""
        headers = {"Content-Type": "application/json"}
        api_key = settings.embeddings_api_key or settings.openai_api_key
        if api_key is not None:
            headers["Authorization"] = f"Bearer {api_key.get_secret_value()}"
        return headers


def get_embedder() -> _EmbeddingApiClient:
    """Return the process-wide embedding API client singleton."""
    global _EMBEDDER_INSTANCE
    if _EMBEDDER_INSTANCE is None:
        with _EMBEDDER_LOCK:
            if _EMBEDDER_INSTANCE is None:
                _EMBEDDER_INSTANCE = _EmbeddingApiClient()
    return _EMBEDDER_INSTANCE


def reset_embedder_for_tests() -> None:
    """Drop the cached singleton. Only used by the test suite."""
    global _EMBEDDER_INSTANCE
    with _EMBEDDER_LOCK:
        _EMBEDDER_INSTANCE = None
