"""Request / response models for the ``knowledge`` HTTP API and the published
in-process interface.

The read models mirror the ORM rows; :class:`SpeciesMetricsBundle` is the shape
other contexts (``assessment``, ``advice``) consume as JSON.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# species
# --------------------------------------------------------------------------- #


class SpeciesCreate(BaseModel):
    species_code: str = Field(min_length=1, max_length=64)
    scientific_name: str = Field(min_length=1, max_length=200)
    common_name: str | None = Field(default=None, max_length=200)


class SpeciesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    species_code: str
    scientific_name: str
    common_name: str | None


# --------------------------------------------------------------------------- #
# research_document
# --------------------------------------------------------------------------- #


class DocumentCreate(BaseModel):
    species_code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    author: str = Field(min_length=1, max_length=120)
    source_url: str | None = None
    source_note: str | None = None


class DocumentUpdate(BaseModel):
    """Every field optional — only what is sent is changed."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1)
    author: str | None = Field(default=None, min_length=1, max_length=120)
    source_url: str | None = None
    source_note: str | None = None


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    species_code: str
    title: str
    body: str
    content_hash: str
    author: str
    source_url: str | None
    source_note: str | None
    created_at: datetime


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ordering: int
    instruction: str
    urgency: str
    expect_typical_hours: int
    expect_max_hours: int
    expected_signal: str | None


class ExemplarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    storage_key: str
    content_type: str | None
    label: dict[str, Any] | None
    origin: str
    license: str | None
    caption: str | None


class MetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    care_need: str
    crop: str
    priority: int
    is_screening: bool
    question: str
    worse_looks_like: str
    better_looks_like: str
    not_this: str
    evidence_quote: str | None
    actions: list[ActionRead]
    exemplars: list[ExemplarRead]


class MetricSetSummary(BaseModel):
    id: uuid.UUID
    research_document_id: uuid.UUID
    llm_model: str
    prompt_version: str | None
    status: str
    generated_at: datetime
    approved_by: str | None
    approved_at: datetime | None
    is_stale: bool
    metric_count: int


class MetricSetDetail(MetricSetSummary):
    metrics: list[MetricRead]


class SpeciesMetricsBundle(BaseModel):
    """Published payload: the current metrics + actions for one species."""

    species_code: str
    metric_set_id: uuid.UUID
    status: str
    is_stale: bool
    generated_at: datetime
    metrics: list[MetricRead]
