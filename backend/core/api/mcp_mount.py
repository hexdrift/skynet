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

from fastmcp import FastMCP
from fastmcp.server import dependencies as _fastmcp_deps
from fastmcp.server.providers.openapi import components as _fastmcp_openapi_components
from fastmcp.server.providers.openapi.components import (
    OpenAPIResource,
    OpenAPIResourceTemplate,
    OpenAPITool,
)
from fastmcp.server.providers.openapi.routing import MCPType, RouteMap
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastmcp.utilities.openapi.models import HTTPRoute

logger = logging.getLogger(__name__)

# FastMCP's OpenAPITool/OpenAPIResource forward MCP request headers to the
# inner ASGI call via ``get_http_headers()``, which strips ``authorization``
# by default (see fastmcp/server/dependencies.py: it lives in the
# ``exclude_headers`` set). Our downstream is the same FastAPI app and every
# agent-tagged route depends on ``get_authenticated_user``, so without the
# bearer token every tool call returns 401 ``auth.missing_token``. Override
# the lookup in the components module so the header flows through.
_fastmcp_openapi_components.get_http_headers = partial(
    _fastmcp_deps.get_http_headers, include={"authorization"}
)

AGENT_TAG = "agent"

_MAX_DESCRIPTION_CHARS = 240
_SCHEMA_NOISE_KEYS = frozenset({"examples", "example", "title"})

# REST semantics carry an honest approval signal the OpenAPI projection drops:
# a read is safe, a delete is destructive, any other write mutates state. We
# surface that as MCP tool annotations so downstream consumers (and the
# optimizer's severity capture) read a real hint instead of fabricating one.
_READ_ONLY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_DESTRUCTIVE_METHODS = frozenset({"DELETE"})
_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH"})

# A route may author its own MCP annotations the same way its docstring authors
# the description: by declaring partial hint fields under this OpenAPI extension
# (``openapi_extra={_MCP_ANNOTATIONS_EXTENSION: {"destructiveHint": True}}``).
# FastMCP surfaces ``x-`` operation extensions on ``HTTPRoute.extensions``; the
# authored fields merge over the method default, so a body-carrying route whose
# verb understates its effect (a POST that deletes) can state the truth.
_MCP_ANNOTATIONS_EXTENSION = "x-mcp-annotations"


def _annotations_for_method(method: str) -> ToolAnnotations | None:
    """Derive MCP tool annotations from an HTTP method, or ``None`` if unmapped.

    Args:
        method: The route's HTTP verb (e.g. ``"GET"``).

    Returns:
        A ``ToolAnnotations`` whose read-only / destructive hints reflect the
        method's REST semantics, or ``None`` for verbs with no clear hint.
    """
    if method in _READ_ONLY_METHODS:
        return ToolAnnotations(readOnlyHint=True)
    if method in _DESTRUCTIVE_METHODS:
        return ToolAnnotations(readOnlyHint=False, destructiveHint=True)
    if method in _MUTATING_METHODS:
        return ToolAnnotations(readOnlyHint=False, destructiveHint=False)
    return None


def _annotations_for_route(route: HTTPRoute) -> ToolAnnotations | None:
    """Resolve a route's MCP annotations from its HTTP method and authored hints.

    The HTTP verb supplies a default hint (:func:`_annotations_for_method`); a
    route may override or extend it by authoring partial annotation fields under
    the ``x-mcp-annotations`` OpenAPI extension, which merge on top. This lets a
    route whose verb understates its effect — a POST that deletes — declare
    ``destructiveHint`` explicitly, the same way its docstring authors the
    description, rather than relying on method derivation alone.

    Args:
        route: The originating FastAPI HTTP route metadata.

    Returns:
        The resolved ``ToolAnnotations``, or ``None`` when neither the method
        nor the route authors any hint.
    """
    base = _annotations_for_method(route.method)
    authored = route.extensions.get(_MCP_ANNOTATIONS_EXTENSION)
    if not authored:
        return base
    fields = base.model_dump(exclude_none=True) if base else {}
    fields.update(authored)
    return ToolAnnotations(**fields)


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
        if component.annotations is None:
            component.annotations = _annotations_for_route(route)


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
