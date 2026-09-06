"""Execution code for ``advice`` — the diagnosis and action-ranking call.

Owner: TODO

This is what ``src/advice`` calls at request time: resolve the production
prompt(s), call the external LLM, parse the answer, trace it into the advice
Langfuse project. If the flow grows into a multi-step agent, its structure lives
in this package as code — Langfuse versions prompts, not graphs.

Text only: verdicts, severities, evidence sentences and history go out — never
plant imagery.

Inputs are plain values — ``mlops`` must not import a bounded context, so the
calling context flattens its own models onto :class:`AdviceInput`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mlops.settings import PRODUCTION_LABEL


@dataclass(frozen=True)
class AdviceInput:
    """What ``src/advice`` passes in.

    TODO: verdicts, history, and the candidate actions from ``knowledge`` that
    the model ranks rather than invents.
    """


@dataclass(frozen=True)
class AdviceResult:
    """What comes back.

    TODO: diagnosis, ranked actions, rationale, citations.
    """

    #: Langfuse trace id, so the caller can correlate its own row with the run.
    trace_id: str | None = None


def generate_advice(
    payload: AdviceInput,
    *,
    label: str | None = PRODUCTION_LABEL,
    version: int | None = None,
    overrides: dict[str, Any] | None = None,
) -> AdviceResult:
    """Produce a diagnosis and ranked actions.

    ``label`` / ``version`` / ``overrides`` exist so ``experiment.py`` can pin a
    prompt version and drive this exact function — experiments and production
    then share one code path. The request path passes none of them.
    """
    raise NotImplementedError
