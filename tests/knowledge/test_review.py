"""Human review: the verdict is the record, and the mirror to Langfuse is a copy.

Nothing automatic can judge whether a probe is a good probe, so a person's
approve/reject *is* the quality signal. Two properties matter here: the verdict
is stored durably in our own schema, and the copy sent to Langfuse can fail
without taking the reviewer's request down with it.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from knowledge import review, service
from knowledge.models import ProbeSet


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture what would have been sent to Langfuse."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(review, "record_review", lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def draft(
    session_factory: sessionmaker[Session], seed_full: Callable[..., Any]
) -> ProbeSet:
    """A draft set with a generation trace, as the agent would have left it."""
    with session_factory() as session:
        _, probe_set, _ = seed_full(session, status="draft")
        probe_set.langfuse_trace_id = "0123456789abcdef0123456789abcdef"
        session.commit()
        session.refresh(probe_set)
        return probe_set


def test_approving_mirrors_the_verdict_to_the_generation_trace(
    client: TestClient, draft: ProbeSet, recorded: list[dict[str, Any]]
) -> None:
    response = client.post(f"/knowledge/probe-sets/{draft.id}/approve")

    assert response.status_code == 200
    assert response.json()["approved_by"] == "ops@example.com"
    assert recorded == [
        {
            "trace_id": "0123456789abcdef0123456789abcdef",
            "verdict": "approved",
            "comment": None,
            "reviewer": "ops@example.com",
        }
    ]


def test_rejecting_records_who_refused_it_and_why(
    client: TestClient,
    draft: ProbeSet,
    recorded: list[dict[str, Any]],
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post(
        f"/knowledge/probe-sets/{draft.id}/reject",
        json={"comment": "the not_this guard describes the wrong look-alike"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "archived"
    assert body["rejected_by"] == "ops@example.com"
    assert body["note"] == "the not_this guard describes the wrong look-alike"

    # The row is the record; the Langfuse score is the analytics copy of it.
    with session_factory() as session:
        stored = session.get(ProbeSet, draft.id)
        assert stored is not None
        assert stored.rejected_at is not None
    assert recorded[0]["verdict"] == "rejected"
    assert recorded[0]["comment"] == (
        "the not_this guard describes the wrong look-alike"
    )


def test_a_rejection_must_say_why(client: TestClient, draft: ProbeSet) -> None:
    """The verdict alone teaches the next prompt version nothing."""
    assert client.post(f"/knowledge/probe-sets/{draft.id}/reject").status_code == 422
    assert (
        client.post(
            f"/knowledge/probe-sets/{draft.id}/reject", json={"comment": ""}
        ).status_code
        == 422
    )


def test_only_a_draft_can_be_rejected(
    client: TestClient, session_factory: sessionmaker[Session], seed_full: Any
) -> None:
    """Retiring an approved set is `/archive` — a different act with a different meaning."""
    with session_factory() as session:
        _, approved, _ = seed_full(session, status="approved")

    response = client.post(
        f"/knowledge/probe-sets/{approved.id}/reject", json={"comment": "not good"}
    )

    assert response.status_code == 409


def test_a_set_with_no_trace_is_skipped_rather_than_guessed_at(
    session_factory: sessionmaker[Session],
    seed_full: Any,
    recorded: list[dict[str, Any]],
) -> None:
    """Hand-seeded sets predate the agent; there is nothing to attach a score to."""
    with session_factory() as session:
        _, probe_set, _ = seed_full(session, status="draft")

    review.record_verdict(
        probe_set, verdict=review.ReviewVerdict.APPROVED, reviewer="ops@example.com"
    )

    assert recorded == []
    assert review.trace_url(probe_set) is None


def test_approving_clears_an_earlier_rejection(
    session_factory: sessionmaker[Session], seed_full: Any
) -> None:
    """A row must not carry both verdicts — the later one is the decision."""
    with session_factory() as session:
        _, probe_set, _ = seed_full(session, status="draft")
        service.reject_probe_set(
            session, probe_set, rejected_by="ops@example.com", comment="wrong"
        )
        service.approve_probe_set(session, probe_set, approved_by="ops@example.com")

        assert probe_set.status == "approved"
        assert probe_set.rejected_by is None
        assert probe_set.rejected_at is None
