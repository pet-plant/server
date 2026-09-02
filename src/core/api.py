"""Health endpoints, mounted by ``main_web`` at the application root.

``GET /health`` is a pure liveness check: 200 whenever the process is running.
A readiness check (PostgreSQL / MinIO reachable) will be added here once ``core``
exposes the corresponding probes.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = "ok"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
