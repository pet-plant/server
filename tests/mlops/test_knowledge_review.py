"""The human verdict on its way to Langfuse.

This is the analytics copy of a decision already recorded in the ``knowledge``
schema, so the contract is: write it under one stable score name, and never let
a failure here surface to the person who made the decision.
"""

from typing import Any

import pytest

from mlops.knowledge import review


class FakeClient:
    def __init__(self) -> None:
        self.scores: list[dict[str, Any]] = []
        self.flushed = 0

    def create_score(self, **kwargs: Any) -> None:
        self.scores.append(kwargs)

    def flush(self) -> None:
        self.flushed += 1


@pytest.fixture
def langfuse(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    client = FakeClient()
    monkeypatch.setattr(review, "is_configured", lambda _: True)
    monkeypatch.setattr(review, "get_client", lambda _: client)
    return client


def test_a_verdict_becomes_a_categorical_score_on_the_trace(
    langfuse: FakeClient,
) -> None:
    review.record_review(
        trace_id="0123456789abcdef0123456789abcdef",
        verdict=review.ReviewVerdict.REJECTED,
        comment="the not_this guard describes the wrong look-alike",
        reviewer="ops@example.com",
    )

    assert langfuse.scores == [
        {
            "name": review.REVIEW_SCORE,
            "value": "rejected",
            "data_type": "CATEGORICAL",
            "trace_id": "0123456789abcdef0123456789abcdef",
            "comment": "the not_this guard describes the wrong look-alike",
            "metadata": {"reviewer": "ops@example.com"},
        }
    ]
    # Reviews arrive one at a time from a request; without a flush the score
    # sits in the background queue until something else happens to send it.
    assert langfuse.flushed == 1


def test_the_score_name_is_the_same_for_both_verdicts(langfuse: FakeClient) -> None:
    """Two names would split one signal across two columns in the comparison view."""
    review.record_review(trace_id="a", verdict=review.ReviewVerdict.APPROVED)
    review.record_review(trace_id="b", verdict=review.ReviewVerdict.REJECTED)

    assert {s["name"] for s in langfuse.scores} == {review.REVIEW_SCORE}


def test_an_outage_is_swallowed_so_the_reviewer_is_never_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decision is already durable in Postgres; losing the copy is survivable."""

    def _down(_: Any) -> Any:
        raise RuntimeError("langfuse unreachable")

    monkeypatch.setattr(review, "is_configured", lambda _: True)
    monkeypatch.setattr(review, "get_client", _down)

    review.record_review(trace_id="a", verdict=review.ReviewVerdict.APPROVED)


def test_nothing_is_sent_when_langfuse_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local run with no keys must not try, and must not warn about it either."""
    monkeypatch.setattr(review, "is_configured", lambda _: False)
    monkeypatch.setattr(
        review, "get_client", lambda _: pytest.fail("should not be reached")
    )

    review.record_review(trace_id="a", verdict=review.ReviewVerdict.APPROVED)
    assert review.trace_url("a") is None
