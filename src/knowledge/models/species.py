"""``species`` — the plant species catalogue (one row per supported plant)."""

from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from knowledge.db import KNOWLEDGE_SCHEMA, Base

if TYPE_CHECKING:
    from knowledge.models.document import ResearchDocument


class Species(Base):
    __tablename__ = "species"
    __table_args__ = {"schema": KNOWLEDGE_SCHEMA}

    species_code: Mapped[str] = mapped_column(Text, primary_key=True)  # 'spath'
    scientific_name: Mapped[str] = mapped_column(Text, nullable=False)
    common_name: Mapped[str | None] = mapped_column(Text)

    documents: Mapped[list["ResearchDocument"]] = relationship(back_populates="species")

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"<Species {self.species_code!r}>"
