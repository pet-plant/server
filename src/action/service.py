"""Persistence for the ``action`` context.

No HTTP concerns here. ``companion``'s care plan / action ids are stored as
received: that context publishes no interface to check them against yet.
"""

import uuid
from collections.abc import Collection
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from action.db import utcnow
from action.models import CareEvent
from action.schemas import (
    ActionCompletedCreate,
    CareEventCreate,
    CareEventType,
    CarePlanProgress,
    CompletedAction,
)

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


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #


def list_events(
    session: Session,
    plant_id: uuid.UUID,
    *,
    since: datetime | None = None,
    event_types: Collection[CareEventType] | None = None,
    limit: int | None = None,
) -> list[CareEvent]:
    """The plant's events, oldest first; with ``limit``, only the most recent ones."""
    stmt = select(CareEvent).where(CareEvent.plant_id == plant_id)
    if since is not None:
        stmt = stmt.where(CareEvent.occurred_at >= since)
    if event_types is not None:
        stmt = stmt.where(CareEvent.event_type.in_(list(event_types)))
    stmt = stmt.order_by(CareEvent.occurred_at.desc(), CareEvent.recorded_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(reversed(session.scalars(stmt).all()))


def last_watered_at(session: Session, plant_id: uuid.UUID) -> datetime | None:
    """When the plant was last watered, or ``None`` if never recorded."""
    return session.scalar(
        select(func.max(CareEvent.occurred_at)).where(
            CareEvent.plant_id == plant_id,
            CareEvent.event_type == CareEventType.WATERED,
        )
    )


def get_care_plan_progress(
    session: Session, plant_id: uuid.UUID, care_plan_id: str
) -> CarePlanProgress:
    """The steps of ``care_plan_id`` done so far; a step pressed twice counts once."""
    events = session.scalars(
        select(CareEvent)
        .where(
            CareEvent.plant_id == plant_id,
            CareEvent.care_plan_id == care_plan_id,
            CareEvent.event_type == CareEventType.ACTION_COMPLETED,
        )
        .order_by(CareEvent.occurred_at, CareEvent.recorded_at)
    ).all()
    first_by_action: dict[str, CompletedAction] = {}
    for event in events:
        if event.action_id is not None and event.action_id not in first_by_action:
            first_by_action[event.action_id] = CompletedAction(
                action_id=event.action_id,
                action_type=event.action_type,
                completed_at=event.occurred_at,
                event_id=event.id,
            )
    return CarePlanProgress(
        plant_id=plant_id,
        care_plan_id=care_plan_id,
        completed_actions=list(first_by_action.values()),
        last_watered_at=last_watered_at(session, plant_id),
    )


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #


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
