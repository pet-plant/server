"""``/action`` router — record the care the owner reports from the GUI, and
show how far a care plan has got.

Each route comes in two forms, one per caller:

- ``/action/plants/{plant_id}/…`` — a signed-in owner (web client).
  Another owner's plant answers 404, not 403, so ids cannot be probed.
- ``/action/devices/me/…`` — a paired planter (its own display), for the
  plant bound to it.

Recording answers ``201`` with the new event, or ``200`` with the earlier one
when the same ``client_event_id`` was already recorded for the plant. Mounted
by ``main_web``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from action import service
from action.models import CareEvent
from action.schemas import CareEventCreate, CareEventRead, CarePlanProgress
from core.db import get_session
from core.devices import CurrentDevice
from core.users import CurrentUser, User
from registry import PlantRead, get_plant, get_plant_by_device

router = APIRouter(prefix="/action", tags=["action"])

SessionDep = Annotated[Session, Depends(get_session)]
CarePlanId = Annotated[str, Path(min_length=1, max_length=64)]


def _owned_plant_or_404(session: Session, plant_id: uuid.UUID, user: User) -> PlantRead:
    plant = get_plant(session, plant_id)
    if plant is None or not (user.is_superuser or plant.owner_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plant not found")
    return plant


def _device_plant_or_404(session: Session, physical_id: str) -> PlantRead:
    plant = get_plant_by_device(session, physical_id)
    if plant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No plant bound to this device")
    return plant


def _record(
    session: Session,
    plant_id: uuid.UUID,
    payload: CareEventCreate,
    response: Response,
    *,
    user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
) -> CareEvent:
    try:
        event, created = service.record_event(
            session, plant_id, payload, user_id=user_id, device_id=device_id
        )
    except service.OccurredInFutureError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "occurred_at is in the future"
        ) from None
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return event


@router.post(
    "/plants/{plant_id}/events",
    response_model=CareEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Owner: record a completed care action or a watering",
)
def record_plant_event(
    plant_id: uuid.UUID,
    payload: CareEventCreate,
    response: Response,
    session: SessionDep,
    user: CurrentUser,
) -> CareEvent:
    plant = _owned_plant_or_404(session, plant_id, user)
    if not plant.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plant is archived")
    return _record(session, plant.id, payload, response, user_id=user.id)


@router.get(
    "/plants/{plant_id}/care-plans/{care_plan_id}/progress",
    response_model=CarePlanProgress,
    summary="Owner: the steps of a care plan done so far",
)
def get_plant_care_plan_progress(
    plant_id: uuid.UUID,
    care_plan_id: CarePlanId,
    session: SessionDep,
    user: CurrentUser,
) -> CarePlanProgress:
    plant = _owned_plant_or_404(session, plant_id, user)
    return service.get_care_plan_progress(session, plant.id, care_plan_id)


@router.post(
    "/devices/me/events",
    response_model=CareEventRead,
    status_code=status.HTTP_201_CREATED,
    summary="Device: record a care event for the plant I show",
)
def record_device_event(
    payload: CareEventCreate,
    response: Response,
    session: SessionDep,
    device: CurrentDevice,
) -> CareEvent:
    plant = _device_plant_or_404(session, device.physical_id)
    return _record(session, plant.id, payload, response, device_id=device.id)


@router.get(
    "/devices/me/care-plans/{care_plan_id}/progress",
    response_model=CarePlanProgress,
    summary="Device: the steps of a care plan done so far, for the plant I show",
)
def get_device_care_plan_progress(
    care_plan_id: CarePlanId,
    session: SessionDep,
    device: CurrentDevice,
) -> CarePlanProgress:
    plant = _device_plant_or_404(session, device.physical_id)
    return service.get_care_plan_progress(session, plant.id, care_plan_id)
