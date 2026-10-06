"""Published in-process interface for other bounded contexts.

``advice`` reads what the owner has done for a plant (completed care plan
steps, waterings) here instead of reaching into the ``action`` schema. Return
values are Pydantic models that serialise straight to JSON
(``event.model_dump(mode="json")``).
"""

import uuid
from collections.abc import Collection
from datetime import datetime

from sqlalchemy.orm import Session

from action import service
from action.schemas import CareEventRead, CareEventType


def list_care_events(
    session: Session,
    plant_id: uuid.UUID,
    *,
    since: datetime | None = None,
    event_types: Collection[CareEventType] | None = None,
    limit: int | None = None,
) -> list[CareEventRead]:
    """The care recorded for a plant, oldest first (by ``occurred_at``).

    ``since`` keeps events that occurred at or after it, ``event_types`` keeps
    those kinds only, and ``limit`` keeps the most recent ``limit`` of what is
    left — still returned oldest first. An unknown plant has no events.
    """
    return [
        CareEventRead.model_validate(event)
        for event in service.list_events(
            session, plant_id, since=since, event_types=event_types, limit=limit
        )
    ]
