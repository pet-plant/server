"""``metric_set`` / ``metric`` — the LLM output.

``metric_set`` is one generation run: it records which research document was fed
in, which model produced it, and the human approval that follows. Each ``metric``
is a single-question probe the assessment pipeline later runs against the VLM.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.db import KNOWLEDGE_SCHEMA, Base, utcnow

if TYPE_CHECKING:
    from knowledge.models.action import MetricAction
    from knowledge.models.document import ResearchDocument
    from knowledge.models.exemplar import MetricExemplar


class MetricSet(Base):
    __tablename__ = "metric_set"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    research_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(f"{KNOWLEDGE_SCHEMA}.research_document.id"),
        nullable=False,
    )
    # Hash of research_document.body at generation time (see the freshness view).
    source_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)  # 'gpt-4o-2024-11-20'
    prompt_version: Mapped[str | None] = mapped_column(Text)
    # 'draft' | 'approved' | 'archived'
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    approved_by: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    research_document: Mapped["ResearchDocument"] = relationship(
        back_populates="metric_sets"
    )
    metrics: Mapped[list["Metric"]] = relationship(
        back_populates="metric_set",
        cascade="all, delete-orphan",
        order_by="Metric.priority",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<MetricSet {self.id} {self.status}>"


class Metric(Base):
    __tablename__ = "metric"
    __table_args__ = (
        UniqueConstraint("metric_set_id", "slug", name="uq_metric_set_slug"),
        {"schema": KNOWLEDGE_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    metric_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{KNOWLEDGE_SCHEMA}.metric_set.id"), nullable=False
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False)  # 'water_deficit.leaf_droop'
    care_need: Mapped[str] = mapped_column(Text, nullable=False)  # 'water_deficit'
    crop: Mapped[str] = mapped_column(Text, nullable=False)  # 'whole_plant'
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_screening: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    worse_looks_like: Mapped[str] = mapped_column(Text, nullable=False)
    better_looks_like: Mapped[str] = mapped_column(Text, nullable=False)
    not_this: Mapped[str] = mapped_column(Text, nullable=False)  # over-detection guard
    # The span of research_document.body this metric was generated from.
    evidence_quote: Mapped[str | None] = mapped_column(Text)

    metric_set: Mapped["MetricSet"] = relationship(back_populates="metrics")
    actions: Mapped[list["MetricAction"]] = relationship(
        back_populates="metric",
        cascade="all, delete-orphan",
        order_by="MetricAction.ordering",
    )
    exemplars: Mapped[list["MetricExemplar"]] = relationship(
        back_populates="metric",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Metric {self.slug!r}>"
