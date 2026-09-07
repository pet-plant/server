"""Human evaluation of generated probe sets.

Owner: TODO

**There is no automatic quality metric here, and that is deliberate.** Whether a
probe is a *good* probe — the right care need, a question a VLM can actually
answer from one photograph, an over-detection guard that guards the right thing
— is a botanical judgement. No scorer we could write would measure it, and one
that pretended to would be worse than none: it would move a `production` label
on evidence nobody believes.

So the loop is: generate → a person reads the draft → their verdict comes back
here as a **Langfuse score on the generation's trace**. Over time that is a real
dataset — every prompt version carries the human accept-rate of what it produced,
side by side in the Langfuse UI, and a prompt change can be judged on it.

What *is* automated lives in :mod:`mlops.knowledge.evaluators`: schema
validation and evidence grounding. Those measure well-formedness, never quality.

## Where the verdict comes from

``knowledge`` already has the review step — a superuser approves or rejects a
draft probe set. :mod:`knowledge.review` calls this when they do, so the
evaluation surface is the authoring UI people already use rather than a second
place to remember. Reviewing in the Langfuse UI directly (annotation queues)
writes the same score under the same name, so the two agree.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Final

from mlops.client import get_client, is_configured
from mlops.settings import Component

logger = logging.getLogger(__name__)

COMPONENT: Final = Component.KNOWLEDGE

#: The score a human review writes. One name, whether the verdict came from the
#: ``knowledge`` API or from an annotation queue in the Langfuse UI — otherwise
#: the comparison view splits one signal across two columns.
REVIEW_SCORE: Final[str] = "probe_set_human_review"


class ReviewVerdict(StrEnum):
    """A reviewer's judgement of one generated probe set."""

    #: Botanically sound and usable as it stands.
    APPROVED = "approved"
    #: Wrong, unusable, or not supported by the research document.
    REJECTED = "rejected"


def record_review(
    *,
    trace_id: str,
    verdict: ReviewVerdict,
    comment: str | None = None,
    reviewer: str | None = None,
) -> None:
    """Attach a human verdict to the generation trace it judges.

    ``comment`` is the valuable half — *why* a set was rejected is what the next
    prompt version has to fix, and the verdict alone cannot say it. Ask for one
    on rejection.

    ``reviewer`` identifies who judged, for accountability on a self-hosted
    Langfuse that is part of this project. It is stored as score metadata, not
    as the trace's ``user_id``, which belongs to the plant owner concept.

    Best-effort by design: a review is recorded in the ``knowledge`` schema
    first, and losing the copy in Langfuse must never fail the reviewer's
    request. Failures are logged, not raised.
    """
    if not is_configured(COMPONENT):
        logger.debug("Langfuse not configured; skipping review score for %s", trace_id)
        return
    try:
        client = get_client(COMPONENT)
        client.create_score(
            name=REVIEW_SCORE,
            value=verdict.value,
            data_type="CATEGORICAL",
            trace_id=trace_id,
            comment=comment,
            metadata={"reviewer": reviewer} if reviewer else None,
        )
        client.flush()
    except Exception:  # noqa: BLE001 - never break the review on a telemetry fault
        logger.warning(
            "Failed to record the human review of trace %s in Langfuse",
            trace_id,
            exc_info=True,
        )


def trace_url(trace_id: str) -> str | None:
    """A deep link to the generation trace, for a reviewer who wants the detail.

    The draft probes are visible in the ``knowledge`` API; this is for what sits
    behind them — the prompt version used, the raw model output, how many repair
    rounds it took. Returns ``None`` when Langfuse is not configured.
    """
    if not is_configured(COMPONENT):
        return None
    try:
        return get_client(COMPONENT).get_trace_url(trace_id=trace_id)
    except Exception:  # noqa: BLE001 - a missing link is not worth an error
        logger.debug("Could not build a trace URL for %s", trace_id, exc_info=True)
        return None
