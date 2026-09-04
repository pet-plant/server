"""``research_document`` — the human-authored plant research.

A person compiles what they have found about a species (watering, light,
pruning, …) into one text. That text is the sole input the LLM uses to generate
a :class:`~knowledge.models.metric.MetricSet`.

Rows are **append-only**: to revise the text you insert a new row for the same
``species_code`` (the newest ``created_at`` is the current one), never edit
``body`` in place. ``content_hash`` (SHA-256 of ``body``) is snapshotted onto
every ``metric_set`` so drift can be detected — see the ``metric_set_freshness``
view in :mod:`knowledge.db`.

One current document per species is assumed; a grouping key would be needed to
keep several topic-scoped documents per species side by side.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.db import KNOWLEDGE_SCHEMA, Base, utcnow
from knowledge.hashing import content_hash

if TYPE_CHECKING:
    from knowledge.models.metric import MetricSet
    from knowledge.models.species import Species


def _default_content_hash(context: Any) -> str:
    """Derive ``content_hash`` from the ``body`` being inserted."""
    return content_hash(context.get_current_parameters()["body"])


class ResearchDocument(Base):
    __tablename__ = "research_document"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    species_code: Mapped[str] = mapped_column(
        Text, ForeignKey(f"{KNOWLEDGE_SCHEMA}.species.species_code"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # The researched text, exactly as fed to the LLM.
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA-256 (hex) of ``body``; filled in automatically from the value above.
    content_hash: Mapped[str] = mapped_column(
        Text, nullable=False, default=_default_content_hash
    )
    author: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    species: Mapped["Species"] = relationship(back_populates="documents")
    metric_sets: Mapped[list["MetricSet"]] = relationship(
        back_populates="research_document"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ResearchDocument {self.title!r}>"
