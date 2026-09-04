"""``/knowledge`` router — research-document CRUD and metric inspection.

The LLM generation logic is not wired yet; these endpoints only read and edit
what is already stored. Mounted by ``main_web``.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.db import get_session
from core.users import CurrentUser
from knowledge import service
from knowledge.interface import get_species_metrics as _species_metrics
from knowledge.models import ResearchDocument
from knowledge.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    MetricRead,
    MetricSetDetail,
    MetricSetSummary,
    SpeciesMetricsBundle,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SessionDep = Annotated[Session, Depends(get_session)]


def _document_or_404(session: Session, document_id: uuid.UUID) -> ResearchDocument:
    doc = service.get_document(session, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


# --------------------------------------------------------------------------- #
# research_document CRUD
# --------------------------------------------------------------------------- #


@router.post(
    "/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: DocumentCreate, session: SessionDep, _user: CurrentUser
) -> ResearchDocument:
    try:
        return service.create_document(session, payload)
    except service.UnknownSpeciesError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Unknown species_code"
        ) from None


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    session: SessionDep, _user: CurrentUser, species_code: str | None = None
) -> Sequence[ResearchDocument]:
    return service.list_documents(session, species_code=species_code)


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID, session: SessionDep, _user: CurrentUser
) -> ResearchDocument:
    return _document_or_404(session, document_id)


@router.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: uuid.UUID,
    payload: DocumentUpdate,
    session: SessionDep,
    _user: CurrentUser,
) -> ResearchDocument:
    doc = _document_or_404(session, document_id)
    return service.update_document(session, doc, payload)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID, session: SessionDep, _user: CurrentUser
) -> None:
    doc = _document_or_404(session, document_id)
    try:
        service.delete_document(session, doc)
    except service.DocumentInUseError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Document is referenced by a metric set",
        ) from None


# --------------------------------------------------------------------------- #
# metric inspection
# --------------------------------------------------------------------------- #


@router.get(
    "/species/{species_code}/metric-sets",
    response_model=list[MetricSetSummary],
)
def list_metric_sets(
    species_code: str, session: SessionDep, _user: CurrentUser
) -> list[MetricSetSummary]:
    return [
        MetricSetSummary(
            id=s.id,
            research_document_id=s.research_document_id,
            llm_model=s.llm_model,
            prompt_version=s.prompt_version,
            status=s.status,
            generated_at=s.generated_at,
            approved_by=s.approved_by,
            approved_at=s.approved_at,
            is_stale=stale,
            metric_count=count,
        )
        for s, stale, count in service.list_metric_sets(session, species_code)
    ]


@router.get("/metric-sets/{metric_set_id}", response_model=MetricSetDetail)
def get_metric_set(
    metric_set_id: uuid.UUID, session: SessionDep, _user: CurrentUser
) -> MetricSetDetail:
    metric_set = service.get_metric_set(session, metric_set_id)
    if metric_set is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Metric set not found")
    return MetricSetDetail(
        id=metric_set.id,
        research_document_id=metric_set.research_document_id,
        llm_model=metric_set.llm_model,
        prompt_version=metric_set.prompt_version,
        status=metric_set.status,
        generated_at=metric_set.generated_at,
        approved_by=metric_set.approved_by,
        approved_at=metric_set.approved_at,
        is_stale=service.is_metric_set_stale(session, metric_set.id),
        metric_count=len(metric_set.metrics),
        metrics=[MetricRead.model_validate(m) for m in metric_set.metrics],
    )


@router.get(
    "/species/{species_code}/metrics",
    response_model=SpeciesMetricsBundle,
    summary="Current metrics + actions for a species (same payload as the "
    "in-process interface)",
)
def species_metrics(
    species_code: str, session: SessionDep, _user: CurrentUser
) -> SpeciesMetricsBundle:
    bundle = _species_metrics(session, species_code)
    if bundle is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No approved metric set for this species",
        )
    return bundle
