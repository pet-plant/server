"""``/knowledge`` router — research-document authoring and probe inspection.

Every endpoint is admin-only (``CurrentSuperuser``): this is the authoring
surface, not something plant owners call.

The LLM generation logic is not wired yet; these endpoints only read and add to
what is already stored. Documents are append-only (no edit, no delete) and a
species has at most one approved probe set at a time. Mounted by ``main_web``.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.db import get_session
from core.users import CurrentSuperuser
from knowledge import service
from knowledge.interface import get_species_probes as _species_probes
from knowledge.models import ProbeSet, ResearchDocument, Species
from knowledge.schemas import (
    DocumentCreate,
    DocumentRead,
    ProbeRead,
    ProbeSetDetail,
    ProbeSetSummary,
    SpeciesCreate,
    SpeciesProbesBundle,
    SpeciesRead,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

SessionDep = Annotated[Session, Depends(get_session)]
DocumentStatus = Annotated[
    str | None, Query(alias="status", pattern="^(active|archived)$")
]


def _document_or_404(session: Session, document_id: uuid.UUID) -> ResearchDocument:
    doc = service.get_document(session, document_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


def _probe_set_or_404(session: Session, probe_set_id: uuid.UUID) -> ProbeSet:
    probe_set = service.get_probe_set(session, probe_set_id)
    if probe_set is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Probe set not found")
    return probe_set


def _summary(
    probe_set: ProbeSet, *, is_stale: bool, probe_count: int
) -> ProbeSetSummary:
    return ProbeSetSummary(
        id=probe_set.id,
        species_code=probe_set.species_code,
        research_document_id=probe_set.research_document_id,
        llm_model=probe_set.llm_model,
        prompt_version=probe_set.prompt_version,
        status=probe_set.status,
        generated_at=probe_set.generated_at,
        approved_by=probe_set.approved_by,
        approved_at=probe_set.approved_at,
        archived_at=probe_set.archived_at,
        is_stale=is_stale,
        probe_count=probe_count,
    )


# --------------------------------------------------------------------------- #
# species
# --------------------------------------------------------------------------- #


@router.post(
    "/species",
    response_model=SpeciesRead,
    status_code=status.HTTP_201_CREATED,
)
def create_species(
    payload: SpeciesCreate, session: SessionDep, _user: CurrentSuperuser
) -> Species:
    try:
        return service.create_species(session, payload)
    except service.SpeciesAlreadyExistsError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "species_code already exists"
        ) from None


@router.get("/species", response_model=list[SpeciesRead])
def list_species(session: SessionDep, _user: CurrentSuperuser) -> Sequence[Species]:
    return service.list_species(session)


# --------------------------------------------------------------------------- #
# research_document (append-only)
# --------------------------------------------------------------------------- #


@router.post(
    "/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a research document; the species' previous one is archived",
)
def create_document(
    payload: DocumentCreate, session: SessionDep, _user: CurrentSuperuser
) -> ResearchDocument:
    try:
        return service.create_document(session, payload)
    except service.UnknownSpeciesError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Unknown species_code"
        ) from None


@router.get("/documents", response_model=list[DocumentRead])
def list_documents(
    session: SessionDep,
    _user: CurrentSuperuser,
    species_code: str | None = None,
    doc_status: DocumentStatus = None,
) -> Sequence[ResearchDocument]:
    return service.list_documents(
        session, species_code=species_code, status=doc_status
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID, session: SessionDep, _user: CurrentSuperuser
) -> ResearchDocument:
    return _document_or_404(session, document_id)


# --------------------------------------------------------------------------- #
# probe inspection
# --------------------------------------------------------------------------- #


@router.get(
    "/species/{species_code}/probe-sets",
    response_model=list[ProbeSetSummary],
)
def list_probe_sets(
    species_code: str, session: SessionDep, _user: CurrentSuperuser
) -> list[ProbeSetSummary]:
    return [
        _summary(s, is_stale=stale, probe_count=count)
        for s, stale, count in service.list_probe_sets(session, species_code)
    ]


@router.get("/probe-sets/{probe_set_id}", response_model=ProbeSetDetail)
def get_probe_set(
    probe_set_id: uuid.UUID, session: SessionDep, _user: CurrentSuperuser
) -> ProbeSetDetail:
    probe_set = _probe_set_or_404(session, probe_set_id)
    return ProbeSetDetail(
        **_summary(
            probe_set,
            is_stale=service.is_probe_set_stale(session, probe_set.id),
            probe_count=len(probe_set.probes),
        ).model_dump(),
        probes=[ProbeRead.model_validate(p) for p in probe_set.probes],
    )


@router.post(
    "/probe-sets/{probe_set_id}/approve",
    response_model=ProbeSetSummary,
    summary="Make this the species' approved set (archives the one it replaces)",
)
def approve_probe_set(
    probe_set_id: uuid.UUID, session: SessionDep, user: CurrentSuperuser
) -> ProbeSetSummary:
    probe_set = _probe_set_or_404(session, probe_set_id)
    try:
        service.approve_probe_set(session, probe_set, approved_by=user.email)
    except service.ProbeSetTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return _summary(
        probe_set,
        is_stale=service.is_probe_set_stale(session, probe_set.id),
        probe_count=len(probe_set.probes),
    )


@router.post(
    "/probe-sets/{probe_set_id}/archive",
    response_model=ProbeSetSummary,
    summary="Retire the approved set; the species has none until one is approved",
)
def archive_probe_set(
    probe_set_id: uuid.UUID, session: SessionDep, _user: CurrentSuperuser
) -> ProbeSetSummary:
    probe_set = _probe_set_or_404(session, probe_set_id)
    try:
        service.archive_probe_set(session, probe_set)
    except service.ProbeSetTransitionError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    return _summary(
        probe_set,
        is_stale=service.is_probe_set_stale(session, probe_set.id),
        probe_count=len(probe_set.probes),
    )


@router.get(
    "/species/{species_code}/probes",
    response_model=SpeciesProbesBundle,
    summary="Approved probes + actions for a species (same payload as the "
    "in-process interface)",
)
def species_probes(
    species_code: str, session: SessionDep, _user: CurrentSuperuser
) -> SpeciesProbesBundle:
    bundle = _species_probes(session, species_code)
    if bundle is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No approved probe set for this species",
        )
    return bundle
