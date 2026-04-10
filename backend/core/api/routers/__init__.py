"""Domain routers for the Skynet API.

Each module exposes a ``create_*_router(*, ...)`` factory that returns an
``APIRouter`` wired up with the dependencies it needs. ``create_app`` assembles
them via ``app.include_router(...)``.
"""
