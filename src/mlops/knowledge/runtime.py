"""Execution code for ``knowledge`` — probe generation from a research document.

Owner: TODO

Offline authoring, not the request path: ``src/knowledge`` calls this when
someone generates a probe set for a species, then stores the result as a draft
and puts it through its own human approval.

**Ownership split.** MLOps owns *how the model is asked* — the prompt version and
its hyper-parameters. ``knowledge`` owns *what comes out* — the probes, their
approval, the one-approved-set-per-species rule and staleness tracking. Nothing
here approves anything.

Inputs are plain values — ``mlops`` must not import a bounded context, so the
calling context flattens its own models onto :class:`GenerateProbesInput`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlops.settings import PRODUCTION_LABEL


@dataclass(frozen=True)
class GenerateProbesInput:
    """What ``src/knowledge`` passes in.

    TODO: the species and the research document body, verbatim — its hash is
    what ``knowledge`` snapshots onto the generated set.
    """


@dataclass(frozen=True)
class GenerateProbesResult:
    """What comes back — a draft, before any human review.

    TODO: the generated probes and their actions, plus the model and prompt
    version for provenance.
    """

    #: Langfuse trace id, so the caller can correlate its own row with the run.
    trace_id: str | None = None


def generate_probes(
    payload: GenerateProbesInput,
    *,
    label: str | None = PRODUCTION_LABEL,
    version: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> GenerateProbesResult:
    """Generate a draft probe set from a research document.

    ``label`` / ``version`` / ``overrides`` exist so ``experiment.py`` can pin a
    prompt version and drive this exact function — experiments and production
    then share one code path.
    """
    raise NotImplementedError
