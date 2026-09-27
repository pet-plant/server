"""``/orchestrator`` router — see what the pipeline did, or queue a run by hand.

Superuser only. Runs are normally queued by the schedule
(:mod:`orchestrator.worker`). Mounted by ``main_web``.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.db import get_session
from core.users import CurrentSuperuser
from orchestrator import service
from orchestrator.config import load_config
from orchestrator.db import utcnow
from orchestrator.models import PipelineRun
from orchestrator.schemas import RunCreate, RunRead, ScheduleRead
from orchestrator.stages import STAGES
from registry import get_plant

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

SessionDep = Annotated[Session, Depends(get_session)]
RunStatus = Annotated[
    str | None, Query(alias="status", pattern="^(queued|running|succeeded|failed|skipped)$")
]


@router.get("/runs", response_model=list[RunRead], summary="Runs, newest first")
def list_runs(
    session: SessionDep,
    _user: CurrentSuperuser,
    run_status: RunStatus = None,
    plant_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Sequence[PipelineRun]:
    return service.list_runs(session, status=run_status, plant_id=plant_id, limit=limit)


@router.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: uuid.UUID, session: SessionDep, _user: CurrentSuperuser) -> PipelineRun:
    run = service.get_run(session, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return run


@router.post(
    "/runs",
    response_model=RunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Queue a run for a plant now, outside the schedule",
    description="The loop picks it up on its next tick. 404 for an unknown plant.",
)
def create_run(payload: RunCreate, session: SessionDep, _user: CurrentSuperuser) -> PipelineRun:
    if get_plant(session, payload.plant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown plant")
    run = service.enqueue_run(session, payload.plant_id, utcnow(), trigger="manual")
    if run is None:  # same plant, same microsecond
        raise HTTPException(status.HTTP_409_CONFLICT, "A run for this slot already exists")
    return run


@router.get("/schedule", response_model=ScheduleRead, summary="The schedule in effect")
def read_schedule(_user: CurrentSuperuser) -> ScheduleRead:
    config = load_config()
    return ScheduleRead(
        enabled=config.enabled,
        timezone=str(config.timezone),
        schedule=[t.strftime("%H:%M") for t in config.schedule],
        next_slot=service.next_slot(config, utcnow()),
        catch_up_minutes=int(config.catch_up.total_seconds() // 60),
        stages=[s.name for s in STAGES],
    )
