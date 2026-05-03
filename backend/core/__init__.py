"""Top-level package for the Skynet backend.

Subpackages are imported explicitly by callers (``core.api``,
``core.registry``, ``core.service_gateway``, ``core.storage``,
``core.worker``) so importing this package alone does not pull in the
FastAPI app, the worker engine, or the service gateway. That keeps tools
like Alembic — which only need ``core.storage.models`` — fast and free of
unrelated heavy imports.
"""
