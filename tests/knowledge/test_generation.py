"""Document → draft probe set: the backlog query, the mapping, and the run.

The LLM itself is replaced throughout — ``knowledge`` is not being tested on
whether the model writes good probes (nobody can assert that; that is what the
human review is for), but on whether it finds the right documents, stores what
comes back faithfully, and survives one document blowing up.
"""

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from knowledge import generation, service
from knowledge.models import ResearchDocument, Species
from knowledge.schemas import DocumentCreate
from mlops.knowledge import GenerateProbesResult, ProbeGenerationError, PromptRef
from mlops.knowledge.schemas import (
    GeneratedAction,
    GeneratedProbe,
    GeneratedProbeSet,
)

# --------------------------------------------------------------------------- #
# a stand-in for the agent
# --------------------------------------------------------------------------- #


def _generated(slug: str = "water_deficit.leaf_droop") -> GeneratedProbeSet:
    care_need = slug.split(".")[0]
    return GeneratedProbeSet(
        probes=[
            GeneratedProbe(
                slug=slug,
                care_need=care_need,
                priority=1,
                is_screening=True,
                question="Are the leaves drooping or limp?",
                worse_looks_like="limp, folded, hanging leaves",
                better_looks_like="firm, upright leaves",
                not_this="natural night-time leaf folding",
                evidence_quote="leaves droop when it dries out",
                actions=[
                    GeneratedAction(
                        instruction="Water thoroughly until it drains.",
                        urgency="today",
                        expect_typical_hours=12,
                        expect_max_hours=48,
                        expected_signal="leaf_recovery",
                    ),
                    GeneratedAction(
                        instruction="Check the pot drains freely.",
                        urgency="this_week",
                        expect_typical_hours=24,
                        expect_max_hours=72,
                    ),
                ],
            )
        ]
    )


def _result(**overrides: Any) -> GenerateProbesResult:
    defaults: dict[str, Any] = {
        "probe_set": _generated(),
        "agent_version": "v1",
        "model": "gpt-4o-2024-11-20",
        "prompts": (PromptRef("knowledge/v1/generate-probes", 7),),
        "attempts": 1,
        "trace_id": "0123456789abcdef0123456789abcdef",
    }
    return GenerateProbesResult(**{**defaults, **overrides})


class StubAgent:
    """Stands in for a real agent, recording what it was asked to generate."""

    version = "v1"

    def __init__(self, run: Any) -> None:
        self.calls: list[Any] = []
        self._run = run

    def run(self, payload: Any, **_: Any) -> GenerateProbesResult:
        self.calls.append(payload)
        return self._run(payload)


def install_agent(
    monkeypatch: pytest.MonkeyPatch, run: Any
) -> list[Any]:
    """Point `knowledge` at a stub agent; returns the payloads it receives."""
    agent = StubAgent(run)
    monkeypatch.setattr(generation, "get_agent", lambda version=None: agent)
    return agent.calls


@pytest.fixture
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """A stub agent that always succeeds; returns the calls it saw."""
    return install_agent(monkeypatch, lambda _payload: _result())


@pytest.fixture
def add_document(
    session_factory: sessionmaker[Session],
) -> Callable[..., ResearchDocument]:
    def _add(
        species_code: str = "spath",
        *,
        title: str = "watering",
        body: str = "The leaves droop when it dries out.",
    ) -> ResearchDocument:
        with session_factory() as session:
            if session.get(Species, species_code) is None:
                session.add(
                    Species(species_code=species_code, scientific_name="Spathiphyllum")
                )
                session.commit()
            return service.create_document(
                session,
                DocumentCreate(
                    species_code=species_code, title=title, body=body, author="alice"
                ),
            )

    return _add


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as open_session:
        yield open_session


# --------------------------------------------------------------------------- #
# the backlog query
# --------------------------------------------------------------------------- #


def test_a_document_with_no_probe_set_is_pending(
    session: Session, add_document: Callable[..., ResearchDocument]
) -> None:
    document = add_document()

    pending = service.list_unconverted_documents(session)

    assert [d.id for d in pending] == [document.id]


def test_a_document_that_has_been_converted_is_not_pending(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    document = add_document()
    generation.generate_for_document(session, document)

    assert not service.list_unconverted_documents(session)


def test_a_rejected_draft_does_not_put_its_document_back_in_the_queue(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    """Otherwise a scheduled run regenerates what a person already refused."""
    document = add_document()
    probe_set = generation.generate_for_document(session, document)
    service.reject_probe_set(
        session, probe_set, rejected_by="ops@example.com", comment="wrong care need"
    )

    assert not service.list_unconverted_documents(session)


def test_an_archived_document_is_not_pending(
    session: Session, add_document: Callable[..., ResearchDocument]
) -> None:
    """Superseded research text is history; only the active row gets probes."""
    add_document(body="first text")
    current = add_document(body="second text")

    pending = service.list_unconverted_documents(session)

    assert [d.id for d in pending] == [current.id]


def test_a_revised_document_is_pending_again(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    """Documents are append-only, so a revision is a new row with no set."""
    generation.generate_for_document(session, add_document(body="first text"))
    revised = add_document(body="second text")

    assert [d.id for d in service.list_unconverted_documents(session)] == [revised.id]


def test_the_backlog_can_be_narrowed_and_capped(
    session: Session, add_document: Callable[..., ResearchDocument]
) -> None:
    add_document("spath")
    add_document("ficus", body="Leaves drop in a draught.")

    assert len(service.list_unconverted_documents(session, species_code="spath")) == 1
    assert len(service.list_unconverted_documents(session, limit=1)) == 1


# --------------------------------------------------------------------------- #
# storing what comes back
# --------------------------------------------------------------------------- #


def test_a_generated_set_is_stored_as_a_draft_with_its_provenance(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    document = add_document()

    probe_set = generation.generate_for_document(session, document)

    assert probe_set.status == "draft"  # never approved by a machine
    assert probe_set.research_document_id == document.id
    # Snapshotted so the freshness view can flag the set when the text moves on.
    assert probe_set.source_content_hash == document.content_hash
    assert probe_set.llm_model == "gpt-4o-2024-11-20"
    # Structure and prompt are recorded separately: a regression is one or the
    # other, and a single column could not say which.
    assert probe_set.agent_version == "v1"
    assert probe_set.prompt_version == "knowledge/v1/generate-probes@7"
    assert probe_set.langfuse_trace_id == "0123456789abcdef0123456789abcdef"


def test_probes_and_their_actions_are_mapped_field_for_field(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    probe_set = generation.generate_for_document(session, add_document())

    stored = service.get_probe_set(session, probe_set.id)
    assert stored is not None
    assert len(stored.probes) == 1

    probe = stored.probes[0]
    assert probe.slug == "water_deficit.leaf_droop"
    assert probe.care_need == "water_deficit"
    assert probe.is_screening is True
    assert probe.evidence_quote == "leaves droop when it dries out"
    # `ordering` is positional: the agent's list order is the order to act in.
    assert [(a.ordering, a.urgency) for a in probe.actions] == [
        (0, "today"),
        (1, "this_week"),
    ]


def test_the_agent_is_given_the_document_verbatim(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    """Reformatting would break grounding, the hash snapshot and the quotes."""
    document = add_document(body="Leaves  droop\n\nwhen it dries out.")

    generation.generate_for_document(session, document)

    assert fake_agent[0].document_body == "Leaves  droop\n\nwhen it dries out."
    assert fake_agent[0].scientific_name == "Spathiphyllum"


# --------------------------------------------------------------------------- #
# the run
# --------------------------------------------------------------------------- #


def test_generate_pending_works_through_the_backlog(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    add_document("spath")
    add_document("ficus", body="Leaves drop in a draught.")

    report = generation.generate_pending(session)

    assert report.considered == 2
    assert len(report.generated) == 2
    assert report.failed == []
    assert all(o.probe_count == 1 for o in report.generated)
    assert not service.list_unconverted_documents(session)


def test_one_failing_document_does_not_end_the_run(
    session: Session,
    add_document: Callable[..., ResearchDocument],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that cannot handle one awkward text must not block the other 20."""
    add_document("spath")
    add_document("ficus", body="Leaves drop in a draught.")

    def _generate(payload: Any) -> GenerateProbesResult:
        if payload.species_code == "spath":
            raise ProbeGenerationError(3, ValueError("no valid set"))
        return _result()

    install_agent(monkeypatch, _generate)

    report = generation.generate_pending(session)

    assert report.considered == 2
    assert [o.species_code for o in report.generated] == ["ficus"]
    assert [o.species_code for o in report.failed] == ["spath"]
    assert "ProbeGenerationError" in (report.failed[0].error or "")
    # The failure left no half-written set behind, so it is still pending.
    assert [d.species_code for d in service.list_unconverted_documents(session)] == [
        "spath"
    ]


def test_generate_pending_is_a_no_op_on_an_empty_backlog(
    session: Session, fake_agent: list[Any]
) -> None:
    report = generation.generate_pending(session)

    assert report.considered == 0
    assert fake_agent == []


# --------------------------------------------------------------------------- #
# the endpoints over it
# --------------------------------------------------------------------------- #


def test_generate_endpoint_reports_what_it_did(
    client: TestClient,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    add_document()

    response = client.post("/knowledge/probe-sets/generate")

    assert response.status_code == 200
    body = response.json()
    assert body["considered"] == 1
    assert body["failed"] == []
    assert uuid.UUID(body["generated"][0]["probe_set_id"])


def test_generate_endpoint_reports_failures_without_failing(
    client: TestClient,
    add_document: Callable[..., ResearchDocument],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial run is a 200 with a populated `failed` list — read the body."""
    add_document()

    def _boom(_payload: Any) -> GenerateProbesResult:
        raise ProbeGenerationError(3, ValueError("no valid set"))

    install_agent(monkeypatch, _boom)

    response = client.post("/knowledge/probe-sets/generate")

    assert response.status_code == 200
    assert response.json()["generated"] == []
    assert len(response.json()["failed"]) == 1


def test_generate_endpoint_honours_the_species_filter_and_limit(
    client: TestClient,
    add_document: Callable[..., ResearchDocument],
    fake_agent: list[Any],
) -> None:
    add_document("spath")
    add_document("ficus", body="Leaves drop in a draught.")

    response = client.post(
        "/knowledge/probe-sets/generate", params={"species_code": "ficus", "limit": 1}
    )

    assert response.json()["considered"] == 1
    assert [p.species_code for p in fake_agent] == ["ficus"]


def test_generate_endpoint_rejects_an_unbounded_limit(client: TestClient) -> None:
    """Each document is an LLM call; a request must not take on the whole world."""
    assert (
        client.post("/knowledge/probe-sets/generate", params={"limit": 500})
    ).status_code == 422


def test_pending_documents_endpoint_lists_the_backlog(
    client: TestClient, add_document: Callable[..., ResearchDocument]
) -> None:
    add_document()

    response = client.get("/knowledge/documents/pending")

    assert response.status_code == 200
    assert [d["species_code"] for d in response.json()] == ["spath"]
