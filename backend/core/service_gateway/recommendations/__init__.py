"""Job embedding, task summarization, and similar-run lookup.

:mod:`core` drives the embedding pipeline (``embed_finished_job``) and the
similarity query (``search_similar``). :mod:`embeddings` wraps the
vector-model client and :mod:`summarizer` turns a finished run into the
prose chunk that gets embedded.
"""

from __future__ import annotations

from .core import embed_finished_job, search_similar

__all__ = ["embed_finished_job", "search_similar"]
