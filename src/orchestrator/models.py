"""``pipeline_run`` — the job queue.

One **run** is one plant going through the pipeline for one schedule slot
(``capture → assessment → advice → companion``)::

    queued ──▶ running ──▶ succeeded
                  ├──────▶ skipped    a stage said there was nothing to do
                  └──────▶ failed     a stage raised (not retried)

``current_stage`` is the stage the run is at, or stopped at.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.db import ORCHESTRATOR_SCHEMA, Base, utcnow


class PipelineRun(Base):
    __tablename__ = "pipeline_run"
    __table_args__ = (
        # One run per plant per slot, so a tick that runs twice queues nothing new.
        UniqueConstraint("plant_id", "scheduled_for", name="uq_pipeline_run_plant_slot"),
        {"schema": ORCHESTRATOR_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # ``registry.plant.id`` — resolved through ``registry``'s interface, no FK.
    plant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # The schedule slot (UTC) this run belongs to; ``now`` for a manual run.
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 'schedule' | 'manual'
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="schedule")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued", index=True)
    current_stage: Mapped[str] = mapped_column(Text, nullable=False)
    # Why it ended the way it did: the error, or the skip reason.
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
