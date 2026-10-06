"""Persistence for the ``action`` context.

No HTTP concerns here. ``companion``'s care plan / action ids are stored as
received: that context publishes no interface to check them against yet.
"""

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from action.db import utcnow
from action.models import CareEvent
from action.schemas import ActionCompletedCreate, CareEventCreate

#: How far ahead of the server clock ``occurred_at`` may be (client clock skew).
MAX_CLOCK_SKEW = timedelta(minutes=5)


class OccurredInFutureError(Exception):
    """Raised when ``occurred_at`` is later than now (beyond clock skew)."""


def _get_by_client_event_id(
    session: Session, plant_id: uuid.UUID, client_event_id: str
) -> CareEvent | None:
    return session.scalars(
        select(CareEvent).where(
            CareEvent.plant_id == plant_id, CareEvent.client_event_id == client_event_id
        )
    ).one_or_none()


def record_event(
    session: Session,
    plant_id: uuid.UUID,
    data: CareEventCreate,
    *,
    user_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
) -> tuple[CareEvent, bool]:
    """Append one event; returns ``(event, created)``.

    ``created`` is ``False`` when ``data.client_event_id`` was already recorded
    for this plant — the earlier event is returned unchanged.
    """
    if data.client_event_id is not None:
        existing = _get_by_client_event_id(session, plant_id, data.client_event_id)
        if existing is not None:
            return existing, False

    now = utcnow()
    occurred_at = data.occurred_at or now
    if occurred_at > now + MAX_CLOCK_SKEW:
        raise OccurredInFutureError(occurred_at.isoformat())

    event = CareEvent(
        plant_id=plant_id,
        event_type=data.type,
        care_plan_id=data.care_plan_id,
        details=data.details,
        occurred_at=occurred_at,
        recorded_at=now,
        recorded_by_user_id=user_id,
        recorded_by_device_id=device_id,
        client_event_id=data.client_event_id,
    )
    if isinstance(data, ActionCompletedCreate):
        event.action_id = data.action_id
        event.action_type = data.action_type
    session.add(event)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent retry of the same press won the insert.
        session.rollback()
        if data.client_event_id is None:
            raise
        existing = _get_by_client_event_id(session, plant_id, data.client_event_id)
        if existing is None:
            raise
        return existing, False
    session.refresh(event)
    return event, True
