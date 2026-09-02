"""Web process entrypoint — the FastAPI application.

Run with::

    uv run uvicorn main_web:app --app-dir src --reload

There is no central HTTP layer: each bounded context owns its HTTP surface in
``<context>/api.py`` (exposing ``router: APIRouter``) together with its own
request/response schemas. ``core`` provides the health endpoint. Register each
context's router below as it lands.
"""

from fastapi import FastAPI

from core.api import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pet-Plant API",
        version="0.1.0",
        summary="Cloud backend for Pet-Plant.",
    )

    app.include_router(health_router)

    return app


app = create_app()
