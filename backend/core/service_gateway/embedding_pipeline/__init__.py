"""Job summary embedding pipeline feeding the public explore-map.

:mod:`core` runs the per-job embedding (``embed_finished_job``) and the
startup heal (``backfill_missing_embeddings``). :mod:`embeddings` wraps the
OpenAI-compatible vector-model client and :mod:`summarizer` turns a finished
run into the prose chunk that gets embedded.
"""

from __future__ import annotations

from .core import backfill_missing_embeddings, embed_finished_job

__all__ = ["backfill_missing_embeddings", "embed_finished_job"]
