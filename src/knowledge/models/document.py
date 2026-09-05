"""``research_document`` — the human-authored plant research.

A person compiles what they have found about a species (watering, light,
pruning, …) into one text. That text is the sole input the LLM uses to generate
a :class:`~knowledge.models.probe.ProbeSet`.

Rows are **append-only and never deleted**: to revise the text you insert a new
row for the same ``species_code``, and the row it supersedes is moved to
``status = 'archived'`` rather than overwritten. Exactly one ``active`` document
per species is enforced by a partial unique index; the archived rows stay as the
record of what earlier probe sets were generated from.

``content_hash`` (SHA-256 of ``body``) is snapshotted onto every ``probe_set`` so
drift can be detected — see the ``probe_set_freshness`` view in
:mod:`knowledge.db`.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.db import KNOWLEDGE_SCHEMA, Base, utcnow
from knowledge.hashing import content_hash

if TYPE_CHECKING:
    from knowledge.models.probe import ProbeSet
    from knowledge.models.species import Species


def _default_content_hash(context: Any) -> str:
    """Derive ``content_hash`` from the ``body`` being inserted."""
    return content_hash(context.get_current_parameters()["body"])


#: One active document per species; superseded rows live on as 'archived'.
_ACTIVE_ONLY = text("status = 'active'")


class ResearchDocument(Base):
    __tablename__ = "research_document"
    __table_args__ = (
        # The target of ``probe_set``'s composite FK, so a set's denormalised
        # ``species_code`` always matches the document it was generated from.
        UniqueConstraint("id", "species_code", name="uq_research_document_species"),
        Index(
            "uq_research_document_active_species",
            "species_code",
            unique=True,
            postgresql_where=_ACTIVE_ONLY,
            sqlite_where=_ACTIVE_ONLY,
        ),
        {"schema": KNOWLEDGE_SCHEMA},
    )

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
    # 'active' | 'archived'
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    species: Mapped["Species"] = relationship(back_populates="documents")
    probe_sets: Mapped[list["ProbeSet"]] = relationship(
        back_populates="research_document"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ResearchDocument {self.title!r} {self.status}>"
