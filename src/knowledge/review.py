"""Human review of generated probe sets — the other half of the seam to ``mlops``.

A generated probe set is a draft until a person judges it. That judgement is the
**only** meaningful quality signal this pipeline has: nothing automatic can tell
whether a probe is botanically right, answerable from a single photograph, or
guarding against the right look-alike. :mod:`mlops.knowledge.review` says why at
length.

The judgement is recorded twice, on purpose:

- in the ``knowledge`` schema, as the ``probe_set`` status and its
  ``approved_by`` / ``rejected_by`` stamp — **the record**, and what the rest of
  the system reads;
- in Langfuse, as a score on the generation trace — **the analytics copy**, which
  is what makes "prompt v7 is accepted 80% of the time, v6 was 40%" a question
  anyone can answer.

Only the first is allowed to fail a reviewer's request. Everything here is
best-effort and returns ``None`` rather than raising: a Langfuse outage must not
stop a person approving a probe set.
"""

from __future__ import annotations

from knowledge.models import ProbeSet
from mlops.knowledge import ReviewVerdict, record_review
from mlops.knowledge import trace_url as _trace_url


def record_verdict(
    probe_set: ProbeSet,
    *,
    verdict: ReviewVerdict,
    reviewer: str,
    comment: str | None = None,
) -> None:
    """Send a reviewer's verdict to the generation trace it judges.

    A set with no ``langfuse_trace_id`` — seeded by hand, or generated before
    tracing was configured — is skipped silently; there is nothing to attach to.
    """
    if not probe_set.langfuse_trace_id:
        return
    record_review(
        trace_id=probe_set.langfuse_trace_id,
        verdict=verdict,
        comment=comment,
        reviewer=reviewer,
    )


def trace_url(probe_set: ProbeSet) -> str | None:
    """A link to the generation run behind this set, for the reviewer.

    The probes themselves are in the API response; this is for what produced
    them — the prompt version, the raw output, how many repair rounds it took.
    ``None`` when the set has no trace or Langfuse is not configured.
    """
    if not probe_set.langfuse_trace_id:
        return None
    return _trace_url(probe_set.langfuse_trace_id)
