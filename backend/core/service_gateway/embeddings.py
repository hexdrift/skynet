"""Jina code-embeddings adapter for the recommendation service.

The model (``jinaai/jina-code-embeddings-0.5b`` by default) is loaded
lazily on first use through ``sentence-transformers`` so the app can
start and serve every other endpoint without the 1.5 GB of torch
weights being present. If the extra isn't installed the embedder
silently becomes a no-op — the recommendation endpoint still returns
an empty list and the operator gets one log line explaining why.

MRL ("Matryoshka Representation Learning") truncation: the Jina model
is trained so that the first N dimensions are themselves a valid
embedding. We slice to ``settings.recommendations_embedding_dim``
(default 512) to match the ``vector(512)`` columns in
``job_embeddings``. After truncation we L2-normalize so cosine and
dot product agree, which keeps the pgvector index math simple.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from ..config import settings

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDER_LOCK = threading.Lock()
_EMBEDDER_INSTANCE: "_JinaEmbedder | None" = None


class _JinaEmbedder:
    """Lazy singleton around a sentence-transformers model.

    Use ``get_embedder()`` to access — never construct directly.
    ``encode(text)`` returns a plain ``list[float]`` of length
    ``settings.recommendations_embedding_dim`` or ``None`` if the
    backing model isn't loadable in this process.
    """

    def __init__(self) -> None:
        self._model = None
        self._failed = False
        self._dim = settings.recommendations_embedding_dim

    def _load(self) -> None:
        if self._model is not None or self._failed:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. Recommendations "
                "ingest + search will be disabled until you run "
                "`pip install -e '.[recommendations]'`."
            )
            self._failed = True
            return
        try:
            self._model = SentenceTransformer(
                settings.recommendations_embedding_model,
                trust_remote_code=True,
            )
            logger.info(
                "Loaded embedder %s (truncating to %d dims)",
                settings.recommendations_embedding_model,
                self._dim,
            )
        except Exception as exc:
            logger.warning(
                "Failed to load embedding model %s: %s. Recommendations disabled.",
                settings.recommendations_embedding_model,
                exc,
            )
            self._failed = True

    def available(self) -> bool:
        """True if the encoder has loaded successfully on this process."""
        self._load()
        return self._model is not None

    def encode(self, text: str) -> list[float] | None:
        """Return an MRL-truncated, L2-normalized embedding or ``None``.

        Empty/whitespace input returns ``None`` so callers don't write
        zero-vectors that would pollute the similarity search.
        """
        if not text or not text.strip():
            return None
        self._load()
        if self._model is None:
            return None
        try:
            import numpy as np

            raw = self._model.encode(text, show_progress_bar=False, convert_to_numpy=True)
            vec: np.ndarray = raw[: self._dim]
            norm = float(np.linalg.norm(vec))
            if norm == 0.0:
                return None
            return (vec / norm).astype("float32").tolist()
        except Exception as exc:
            logger.warning("Embedding encode failed: %s", exc)
            return None


def get_embedder() -> _JinaEmbedder:
    """Return the process-wide embedder singleton."""
    global _EMBEDDER_INSTANCE
    if _EMBEDDER_INSTANCE is None:
        with _EMBEDDER_LOCK:
            if _EMBEDDER_INSTANCE is None:
                _EMBEDDER_INSTANCE = _JinaEmbedder()
    return _EMBEDDER_INSTANCE


def reset_embedder_for_tests() -> None:
    """Drop the cached singleton. Only used by the test suite."""
    global _EMBEDDER_INSTANCE
    with _EMBEDDER_LOCK:
        _EMBEDDER_INSTANCE = None
