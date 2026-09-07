"""Turning research documents into draft probe sets.

The seam between this context and ``mlops``. Everything about *how* the model is
asked — the prompt, its version, the hyper-parameters, the validation of what
comes back — belongs to :mod:`mlops.knowledge`. Everything here is about what
this context does with the result: map it onto rows, store it as a **draft**,
and leave it for a person to approve.

**No HTTP anywhere in this module.** :func:`generate_pending` is the function the
``/knowledge/probe-sets/generate`` endpoint calls, and it is the same function a
scheduler will call once probe generation runs on a timer:

.. code-block:: python

    from core.db import SessionLocal
    from knowledge.generation import generate_pending

    with SessionLocal() as session:
        report = generate_pending(session)

It takes a ``Session`` and plain arguments, returns a plain report, and raises
nothing for a single document's failure — everything a background job needs and
nothing a request needs.

Generation is **never automatic past the draft**. A generated set is not usable
until a superuser approves it, and that review is also the project's only real
quality signal — see :mod:`knowledge.review`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from knowledge.models import Probe, ProbeAction, ProbeSet, ResearchDocument, Species
from knowledge.service import list_unconverted_documents
from mlops.client import flush
from mlops.knowledge import (
    GenerateProbesInput,
    GenerateProbesResult,
    get_agent,
)
from mlops.settings import Component

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationOutcome:
    """What happened to one document."""

    document_id: str
    species_code: str
    #: The draft that was created, or ``None`` when generation failed.
    probe_set_id: str | None = None
    probe_count: int = 0
    #: Why it failed, for the job log and the API response. ``None`` on success.
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.probe_set_id is not None


@dataclass(frozen=True)
class GenerationReport:
    """The result of one backfill run."""

    considered: int
    generated: list[GenerationOutcome] = field(default_factory=list)
    failed: list[GenerationOutcome] = field(default_factory=list)


def generate_for_document(
    session: Session, document: ResearchDocument, *, agent_version: str | None = None
) -> ProbeSet:
    """Generate one draft probe set from ``document`` and store it.

    The document's ``content_hash`` is snapshotted onto the set, so the moment
    someone revises the research text the freshness view flags this set as
    stale. Commits on success.

    ``agent_version`` selects a non-default agent implementation — for running
    an older structure against a document, or a new one before it is promoted.
    Leave it unset for ordinary runs; the prompt each agent uses is whatever
    carries the ``production`` label in Langfuse.

    Raises:
        mlops.knowledge.ProbeGenerationError: nothing valid came back.
    """
    species = session.get(Species, document.species_code)
    result = get_agent(agent_version).run(
        GenerateProbesInput(
            species_code=document.species_code,
            scientific_name=(
                species.scientific_name if species else document.species_code
            ),
            common_name=species.common_name if species else None,
            document_title=document.title,
            document_body=document.body,
        ),
    )
    probe_set = _store(session, document, result)
    logger.info(
        "Generated %d probes for %s from document %s (agent %s, %s, %d attempt(s))",
        len(result.probe_set.probes),
        document.species_code,
        document.id,
        result.agent_version,
        result.prompt_ref,
        result.attempts,
    )
    return probe_set


def _store(
    session: Session, document: ResearchDocument, result: GenerateProbesResult
) -> ProbeSet:
    """Map the validated output onto rows. Draft status, always.

    The mapping is deliberately field by field rather than a loop over
    ``model_dump``: the two shapes are allowed to drift — ``mlops`` answers to
    the model, these columns answer to the schema — and a rename on either side
    should surface here as a type error, not as a silently dropped field.
    """
    probe_set = ProbeSet(
        research_document_id=document.id,
        species_code=document.species_code,
        source_content_hash=document.content_hash,
        llm_model=result.model,
        agent_version=result.agent_version,
        prompt_version=result.prompt_ref,
        langfuse_trace_id=result.trace_id,
        status="draft",
    )
    session.add(probe_set)
    session.flush()
    for generated_probe in result.probe_set.probes:
        probe = Probe(
            probe_set_id=probe_set.id,
            slug=generated_probe.slug,
            care_need=generated_probe.care_need,
            priority=generated_probe.priority,
            is_screening=generated_probe.is_screening,
            question=generated_probe.question,
            worse_looks_like=generated_probe.worse_looks_like,
            better_looks_like=generated_probe.better_looks_like,
            not_this=generated_probe.not_this,
            evidence_quote=generated_probe.evidence_quote,
        )
        session.add(probe)
        session.flush()
        for ordering, action in enumerate(generated_probe.actions):
            session.add(
                ProbeAction(
                    probe_id=probe.id,
                    ordering=ordering,
                    instruction=action.instruction,
                    urgency=action.urgency,
                    expect_typical_hours=action.expect_typical_hours,
                    expect_max_hours=action.expect_max_hours,
                    expected_signal=action.expected_signal,
                )
            )
    session.commit()
    session.refresh(probe_set)
    return probe_set


def generate_pending(
    session: Session,
    *,
    species_code: str | None = None,
    limit: int | None = None,
    agent_version: str | None = None,
) -> GenerationReport:
    """Generate a draft for every active document that has no probe set yet.

    The externally-callable entry point: an endpoint calls it now, a scheduler
    will call it later, and neither needs anything the other does not.

    **One document's failure never ends the run.** A model that returns nothing
    valid for one awkward research text must not stop the other twenty from
    being generated, so each document is attempted on its own and its failure is
    recorded in ``report.failed`` rather than raised. Check that list — a run
    that "succeeded" with every document in it is a broken prompt, not a
    successful job.
    """
    documents = list(
        list_unconverted_documents(session, species_code=species_code, limit=limit)
    )
    report = GenerationReport(considered=len(documents))
    for document in documents:
        try:
            probe_set = generate_for_document(
                session, document, agent_version=agent_version
            )
        except Exception as exc:  # noqa: BLE001 - one bad document, not a bad run
            session.rollback()
            logger.warning(
                "Probe generation failed for document %s (%s)",
                document.id,
                document.species_code,
                exc_info=True,
            )
            report.failed.append(
                GenerationOutcome(
                    document_id=str(document.id),
                    species_code=document.species_code,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        report.generated.append(
            GenerationOutcome(
                document_id=str(document.id),
                species_code=document.species_code,
                probe_set_id=str(probe_set.id),
                probe_count=len(probe_set.probes),
            )
        )
    _flush_traces()
    return report


def _flush_traces() -> None:
    """Push the run's traces out before a short-lived process can exit.

    Tracing is asynchronous: a cron invocation that returns from here and exits
    would drop everything still in the queue, and the traces are what the human
    review is later attached to. Harmless in a web process, which would have
    flushed on its own.
    """
    try:
        flush(Component.KNOWLEDGE)
    except Exception:  # noqa: BLE001 - telemetry never fails the job
        logger.debug("Could not flush Langfuse traces", exc_info=True)
