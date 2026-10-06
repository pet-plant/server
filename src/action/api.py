"""``/action`` router — record the care the owner reports from the GUI.

Two ways in, one per caller, same body (:data:`CareEventCreate`):

- ``POST /action/plants/{plant_id}/events`` — a signed-in owner (web client).
  Another owner's plant answers 404, not 403, so ids cannot be probed.
- ``POST /action/devices/me/events`` — a paired planter (its own display),
  for the plant bound to it.

``201`` when the event is recorded, ``200`` with the earlier event when the
same ``client_event_id`` was already recorded for the plant. Mounted by
``main_web``.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from action import service
from action.models import CareEvent
from action.schemas import CareEventCreate, CareEventRead
from core.db import get_session
from core.devices import CurrentDevice
from core.users import CurrentUser
from registry import get_plant, get_plant_by_device

router = APIRouter(prefix="/action", tags=["action"])

SessionDep = Annotated[Session, Depends(get_session)]


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
    plant = get_plant(session, plant_id)
    if plant is None or not (user.is_superuser or plant.owner_id == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plant not found")
    if not plant.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Plant is archived")
    return _record(session, plant.id, payload, response, user_id=user.id)


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
    plant = get_plant_by_device(session, device.physical_id)
    if plant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No plant bound to this device")
    return _record(session, plant.id, payload, response, device_id=device.id)
