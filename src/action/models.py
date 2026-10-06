"""``care_event`` — an append-only log of the care the owner reports doing.

One row per button press in the GUI. Rows are never updated or deleted; any
state (when the plant was last watered, which steps of a care plan are done) is
derived by reading the log.

``event_type`` says what happened, and decides which of the nullable columns
are filled:

- ``action_completed`` — a step of a ``companion`` care plan was marked done:
  ``care_plan_id`` / ``action_id`` (and ``action_type``) are set.
- ``watered`` — the owner watered the plant. Offered whether or not the plant
  has a problem, so ``care_plan_id`` is set only when it was pressed from a
  care card.

A new kind of event is a new ``event_type`` value; anything specific to it
goes in ``details`` (JSON), so the table does not change shape.

``plant_id`` is ``registry.plant.id``, and the care plan / action ids are
``companion``'s (``cp_…`` / ``act_…``). None of them is a database foreign key —
a context never constrains against another context's schema.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from action.db import ACTION_SCHEMA, Base, utcnow

#: Only rows sent with a ``client_event_id`` are deduplicated.
_HAS_CLIENT_EVENT_ID = text("client_event_id IS NOT NULL")


class CareEvent(Base):
    __tablename__ = "care_event"
    __table_args__ = (
        # A retried button press (same client_event_id) is recorded once.
        Index(
            "uq_care_event_plant_client_event",
            "plant_id",
            "client_event_id",
            unique=True,
            postgresql_where=_HAS_CLIENT_EVENT_ID,
            sqlite_where=_HAS_CLIENT_EVENT_ID,
        ),
        # "Latest event of a type for a plant" (e.g. last watered).
        Index("ix_care_event_plant_type_occurred", "plant_id", "event_type", "occurred_at"),
        {"schema": ACTION_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # ``registry.plant.id`` — resolved through ``registry``'s interface, no FK.
    plant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # 'action_completed' | 'watered'
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    # ``companion`` care plan / action ids, as the GUI received them.
    care_plan_id: Mapped[str | None] = mapped_column(Text, index=True)
    action_id: Mapped[str | None] = mapped_column(Text)
    # 'water' | 'move' | 'inspect' | 'other' — the completed action's category.
    action_type: Mapped[str | None] = mapped_column(Text)
    # Event-specific extras (free-form JSON object).
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql")
    )
    # When the owner did it (client clock), and when the server stored it.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    # Who pressed the button: an owner (``auth.users.id``) or a planter
    # (``auth.devices.id``). Exactly one is set.
    recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    recorded_by_device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # Client-generated key so a retried request is not recorded twice.
    client_event_id: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<CareEvent {self.event_type} plant={self.plant_id} {self.id}>"
