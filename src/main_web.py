"""Web process entrypoint — the FastAPI application.

Run with::

    uv run uvicorn main_web:app --app-dir src --reload

There is no central HTTP layer: each bounded context owns its HTTP surface in
``<context>/api.py`` (exposing ``router: APIRouter``) together with its own
request/response schemas. ``core`` provides the health endpoint. Register each
context's router below as it lands.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.api import router as health_router
from core.db import SessionLocal, init_models
from core.users import ensure_admin_user
from core.users import router as auth_router
from knowledge import router as knowledge_router
from knowledge.db import init_models as init_knowledge_models


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Interim: create the `auth` schema + tables on startup until per-schema
    # Alembic migrations land (see `core` README / the `migrate` service in
    # compose.yaml).
    init_models()
    init_knowledge_models()
    # Seed / reconcile the bootstrap admin from ADMIN_* settings.
    with SessionLocal() as session:
        ensure_admin_user(session)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pet-Plant API",
        version="0.1.0",
        summary="Cloud backend for Pet-Plant.",
        lifespan=lifespan,
    )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(knowledge_router)

    return app


app = create_app()
