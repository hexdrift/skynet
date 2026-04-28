"""Shared field names used by both the code and generalist agents.

``REASONING_FIELD`` is the synthetic signature field name DSPy emits for
provider-streamed reasoning chunks. Both agent modules need to recognise
it so they route the chunk through the reasoning channel of the SSE
stream rather than the regular reply channel.
"""

from __future__ import annotations

REASONING_FIELD = "_provider_reasoning"
