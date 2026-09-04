"""``metric_action`` — the remedial actions attached to a metric.

When a metric fires ("water deficit, visible as leaf droop"), these are the
things to do about it, together with how long the effect takes to show —
``expect_max_hours`` is the grace period before the plant is re-alerted.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.db import KNOWLEDGE_SCHEMA, Base

if TYPE_CHECKING:
    from knowledge.models.metric import Metric


class MetricAction(Base):
    __tablename__ = "metric_action"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    metric_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{KNOWLEDGE_SCHEMA}.metric.id"), nullable=False
    )
    ordering: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    # 'today' | 'this_week' | 'this_month'
    urgency: Mapped[str] = mapped_column(Text, nullable=False)
    expect_typical_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    expect_max_hours: Mapped[int] = mapped_column(Integer, nullable=False)  # grace period
    expected_signal: Mapped[str | None] = mapped_column(Text)  # 'leaf_recovery'

    metric: Mapped["Metric"] = relationship(back_populates="actions")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<MetricAction {self.instruction[:32]!r}>"
