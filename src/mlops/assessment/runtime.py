"""Execution code for ``assessment`` — the VLM probe call.

Owner: TODO

This is what ``src/assessment`` calls at request time: resolve the production
prompt, call the on-prem VLM, parse the answer, trace it into the assessment
Langfuse project.

Inputs are plain values — ``mlops`` must not import a bounded context, so the
calling context flattens its own models onto :class:`ProbeInput`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlops.settings import PRODUCTION_LABEL


@dataclass(frozen=True)
class ProbeInput:
    """What ``src/assessment`` passes in.

    TODO: the probe text and the frame to look at, flattened from
    ``knowledge``'s probe definition.
    """


@dataclass(frozen=True)
class ProbeVerdict:
    """What comes back.

    TODO: verdict, severity, evidence, agreement.
    """

    #: Langfuse trace id, so the caller can correlate its own row with the run.
    trace_id: str | None = None


def run_probe(
    probe: ProbeInput,
    *,
    label: str | None = PRODUCTION_LABEL,
    version: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> ProbeVerdict:
    """Run one probe and return its verdict.

    ``label`` / ``version`` / ``overrides`` exist so ``experiment.py`` can pin a
    prompt version and drive this exact function — experiments and production
    then share one code path. The request path passes none of them.
    """
    raise NotImplementedError
