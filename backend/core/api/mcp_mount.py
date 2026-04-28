"""FastMCP mount that exposes tagged REST endpoints as MCP tools.

Only routes carrying the ``"agent"`` OpenAPI tag are projected into the MCP
surface; every other endpoint stays REST-only. New tools are added one
endpoint at a time by appending ``tags=["agent"]`` to the relevant
``APIRouter`` or route decorator — no wiring change required here.

The MCP app is mounted as an ASGI sub-application at ``/mcp`` so it shares
the parent FastAPI's middleware stack (CORS, auth, error envelope). The
REST routes are untouched: the same path served at ``/optimizations`` stays
REST and is, in parallel, surfaced as a tool via ``POST /mcp`` over the
Streamable HTTP transport.

FastMCP's Streamable HTTP transport needs its lifespan started before it
can serve requests. :func:`mount_mcp_on_app` handles this: it builds the
MCP sub-app, mounts it, and wraps the parent FastAPI's lifespan so the
MCP session manager is entered / exited alongside.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import partial
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastmcp.server.providers.openapi.components import (
        OpenAPIResource,
        OpenAPIResourceTemplate,
        OpenAPITool,
    )
    from fastmcp.utilities.openapi.models import HTTPRoute

logger = logging.getLogger(__name__)

AGENT_TAG = "agent"

_MAX_DESCRIPTION_CHARS = 240
_SCHEMA_NOISE_KEYS = frozenset({"examples", "example", "title"})


def _strip_schema_noise(node: Any) -> Any:
    """Recursively strip verbose JSON-schema metadata from ``node``.

    Removes keys that bloat the MCP tool spec without helping the agent
    (``examples``, ``example``, nested ``title``) while preserving type
    information, descriptions on the top node, and required fields.

    Args:
        node: A JSON-schema fragment (dict, list, or scalar).

    Returns:
        A copy of ``node`` with noisy keys recursively removed.
    """
    if isinstance(node, dict):
        return {k: _strip_schema_noise(v) for k, v in node.items() if k not in _SCHEMA_NOISE_KEYS}
    if isinstance(node, list):
        return [_strip_schema_noise(item) for item in node]
    return node


def _trim_tool_spec(
    route: HTTPRoute,
    component: OpenAPITool | OpenAPIResource | OpenAPIResourceTemplate,
) -> None:
    """Shrink an MCP component's description and JSON schemas in place.

    FastMCP folds each route's full docstring and response-model schema
    into the tool spec returned from ``tools/list``. That payload is
    loaded into the agent's context on every ReAct iteration, so trimming
    it directly buys context budget. We keep the first sentence of the
    description (capped at ~240 chars) and strip examples / nested titles
    from the argument and output schemas.

    Args:
        route: The originating FastAPI HTTP route metadata.
        component: The MCP component (tool / resource / resource template) to trim in place.
    """
    from fastmcp.server.providers.openapi.components import OpenAPITool

    if component.description:
        desc = component.description.strip()
        head, sep, _ = desc.partition("\n")
        first_line = head if sep else desc
        if len(first_line) > _MAX_DESCRIPTION_CHARS:
            first_line = first_line[: _MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
        component.description = first_line

    if isinstance(component, OpenAPITool):
        component.parameters = _strip_schema_noise(component.parameters)
        # Output schema is the single biggest tax on the tools/list payload
        # (nested Pydantic models expand into kilobytes per tool) and the
        # ReAct agent receives the actual JSON at runtime anyway. Drop it
        # entirely — we trade machine-readable output validation for context
        # budget, which matters more for small-window models like Minimax.
        component.output_schema = None


def mount_mcp_on_app(app: FastAPI) -> None:
    """Mount the FastMCP sub-app at ``/mcp`` and chain its lifespan.

    Uses :meth:`fastmcp.FastMCP.from_fastapi` with ``tags`` so only
    endpoints explicitly tagged ``"agent"`` become MCP tools. The HTTP
    transport is Streamable HTTP, served at the root of the returned app
    (the parent mounts it under ``/mcp``, yielding ``POST /mcp`` as the
    single tool-protocol endpoint).

    FastMCP's session manager requires an anyio task group that only lives
    while ``mcp_app.lifespan`` is entered. We wrap the parent's current
    lifespan so the MCP app's lifespan is entered alongside — without it,
    every tool call would fail with ``Task group is not initialized``.

    Args:
        app: The parent FastAPI application to mount the MCP sub-app on.
    """
    from fastmcp import FastMCP
    from fastmcp.server.providers.openapi.routing import MCPType, RouteMap

    # FastMCP's ``tags`` kwarg on ``from_fastapi`` only *annotates* MCP
    # components with extra tags — it does not filter. To actually hide
    # non-agent endpoints we configure route maps: the first picks up
    # every ``"agent"``-tagged route as a tool; the catch-all below marks
    # everything else EXCLUDE so it never appears in the MCP surface.
    mcp = FastMCP.from_fastapi(
        app=app,
        name="Skynet",
        route_maps=[
            RouteMap(tags={AGENT_TAG}, mcp_type=MCPType.TOOL),
            RouteMap(mcp_type=MCPType.EXCLUDE),
        ],
        mcp_component_fn=_trim_tool_spec,
    )
    mcp_app = mcp.http_app(path="/")
    app.mount("/mcp", mcp_app)

    parent_lifespan = app.router.lifespan_context
    app.router.lifespan_context = partial(
        _chained_lifespan,
        mcp_app=mcp_app,
        parent_lifespan=parent_lifespan,
    )
    logger.info("FastMCP mounted at /mcp (agent-tagged endpoints only)")


@asynccontextmanager
async def _chained_lifespan(
    scope_app: Any,
    *,
    mcp_app: Any,
    parent_lifespan: Callable[[Any], AbstractAsyncContextManager[Any]],
) -> AsyncIterator[None]:
    """Run the MCP sub-app lifespan alongside the parent FastAPI lifespan.

    FastMCP's session manager requires an anyio task group that only lives
    while the MCP sub-app's lifespan is entered; without chaining, every
    tool call would fail with ``Task group is not initialized``. Binding
    ``mcp_app`` and ``parent_lifespan`` with :func:`functools.partial`
    gives Starlette the expected single-positional-arg lifespan factory
    while keeping this helper at module scope.

    Args:
        scope_app: The parent ASGI application passed by Starlette's lifespan dispatcher.
        mcp_app: The mounted FastMCP sub-app whose lifespan we also enter.
        parent_lifespan: The previously installed lifespan context manager factory.

    Yields:
        ``None`` once both lifespans are active; closes them on exit.
    """
    async with mcp_app.lifespan(mcp_app), parent_lifespan(scope_app):
        yield
