"""Request / response models for the ``/orchestrator`` API."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plant_id: uuid.UUID
    scheduled_for: datetime
    trigger: str
    status: str
    current_stage: str
    detail: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunCreate(BaseModel):
    """Queue a run now, outside the schedule."""

    plant_id: uuid.UUID


class ScheduleRead(BaseModel):
    enabled: bool
    timezone: str
    schedule: list[str]
    next_slot: datetime | None
    catch_up_minutes: int
    stages: list[str]
