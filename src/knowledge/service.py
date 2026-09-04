"""Persistence and read queries for the ``knowledge`` context.

No HTTP concerns and no LLM logic here — this module only stores and reads what
is already in the ``knowledge`` schema.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from knowledge.db import metric_set_freshness
from knowledge.hashing import content_hash
from knowledge.models import Metric, MetricSet, ResearchDocument, Species
from knowledge.schemas import DocumentCreate, DocumentUpdate


class UnknownSpeciesError(Exception):
    """Raised when a document references a ``species_code`` that does not exist."""


class DocumentInUseError(Exception):
    """Raised when deleting a document that a metric set still references."""


# --------------------------------------------------------------------------- #
# research_document CRUD
# --------------------------------------------------------------------------- #


def create_document(session: Session, data: DocumentCreate) -> ResearchDocument:
    if session.get(Species, data.species_code) is None:
        raise UnknownSpeciesError(data.species_code)
    doc = ResearchDocument(
        species_code=data.species_code,
        title=data.title,
        body=data.body,
        author=data.author,
        source_url=data.source_url,
        source_note=data.source_note,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def get_document(session: Session, doc_id: uuid.UUID) -> ResearchDocument | None:
    return session.get(ResearchDocument, doc_id)


def list_documents(
    session: Session, *, species_code: str | None = None
) -> Sequence[ResearchDocument]:
    stmt = select(ResearchDocument).order_by(ResearchDocument.created_at.desc())
    if species_code is not None:
        stmt = stmt.where(ResearchDocument.species_code == species_code)
    return session.scalars(stmt).all()


def update_document(
    session: Session, doc: ResearchDocument, data: DocumentUpdate
) -> ResearchDocument:
    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(doc, key, value)
    if "body" in fields:
        # Keep the hash honest so the freshness view flags affected metric sets.
        doc.content_hash = content_hash(doc.body)
    session.commit()
    session.refresh(doc)
    return doc


def delete_document(session: Session, doc: ResearchDocument) -> None:
    referenced = session.scalar(
        select(func.count())
        .select_from(MetricSet)
        .where(MetricSet.research_document_id == doc.id)
    )
    if referenced:
        raise DocumentInUseError(str(doc.id))
    session.delete(doc)
    session.commit()


# --------------------------------------------------------------------------- #
# metric inspection
# --------------------------------------------------------------------------- #

_METRIC_LOADERS = (
    selectinload(MetricSet.metrics).selectinload(Metric.actions),
    selectinload(MetricSet.metrics).selectinload(Metric.exemplars),
)


def _staleness_map(session: Session) -> dict[uuid.UUID, bool]:
    rows = session.execute(
        select(metric_set_freshness.c.metric_set_id, metric_set_freshness.c.is_stale)
    )
    return {mid: bool(stale) for mid, stale in rows}


def _metric_counts(
    session: Session, set_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not set_ids:
        return {}
    rows = session.execute(
        select(Metric.metric_set_id, func.count())
        .where(Metric.metric_set_id.in_(set_ids))
        .group_by(Metric.metric_set_id)
    )
    return {sid: count for sid, count in rows}


def list_metric_sets(
    session: Session, species_code: str
) -> list[tuple[MetricSet, bool, int]]:
    """All metric sets for a species, newest first, with staleness + metric count."""
    sets = list(
        session.scalars(
            select(MetricSet)
            .join(
                ResearchDocument,
                MetricSet.research_document_id == ResearchDocument.id,
            )
            .where(ResearchDocument.species_code == species_code)
            .order_by(MetricSet.generated_at.desc())
        ).all()
    )
    stale = _staleness_map(session)
    counts = _metric_counts(session, [s.id for s in sets])
    return [(s, stale.get(s.id, False), counts.get(s.id, 0)) for s in sets]


def get_metric_set(session: Session, set_id: uuid.UUID) -> MetricSet | None:
    return session.scalars(
        select(MetricSet).where(MetricSet.id == set_id).options(*_METRIC_LOADERS)
    ).one_or_none()


def get_current_metric_set(
    session: Session, species_code: str, *, status: str = "approved"
) -> MetricSet | None:
    """The most recent metric set for a species in the given ``status``."""
    return session.scalars(
        select(MetricSet)
        .join(
            ResearchDocument,
            MetricSet.research_document_id == ResearchDocument.id,
        )
        .where(
            ResearchDocument.species_code == species_code,
            MetricSet.status == status,
        )
        .order_by(MetricSet.generated_at.desc())
        .options(*_METRIC_LOADERS)
        .limit(1)
    ).one_or_none()


def is_metric_set_stale(session: Session, set_id: uuid.UUID) -> bool:
    return _staleness_map(session).get(set_id, False)
