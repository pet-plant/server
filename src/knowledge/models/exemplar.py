"""``probe_exemplar`` — pointers to few-shot exemplar images.

The image bytes live in the ``exemplars`` MinIO bucket; this row holds the
object key plus the label the model is shown alongside the image.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.db import KNOWLEDGE_SCHEMA, Base, JsonB, utcnow

if TYPE_CHECKING:
    from knowledge.models.probe import Probe


class ProbeExemplar(Base):
    __tablename__ = "probe_exemplar"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    probe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey(f"{KNOWLEDGE_SCHEMA}.probe.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # 'worse_severe' | 'better' …
    # Object key inside the ``exemplars`` bucket.
    storage_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str | None] = mapped_column(Text)  # 'image/jpeg'
    # e.g. {"verdict": "worse", "severity": 2}
    label: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    origin: Mapped[str] = mapped_column(Text, nullable=False)  # 'own_capture' | 'web'
    license: Mapped[str | None] = mapped_column(Text)  # required when origin = 'web'
    caption: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    probe: Mapped["Probe"] = relationship(back_populates="exemplars")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<ProbeExemplar {self.role!r} {self.storage_key!r}>"
