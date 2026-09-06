"""Prompts for the ``advice`` Langfuse project.

Owner: TODO

Keep the prompt names for this project here so ``runtime`` and ``experiment``
resolve them through one place. The prompt bodies and their hyper-parameters
live in Langfuse (a version's ``config``), never in this repository.
"""

from __future__ import annotations

from typing import Any, Final

from mlops.client import get_client
from mlops.settings import PRODUCTION_LABEL, Component

COMPONENT: Final = Component.ADVICE

# TODO: one constant per prompt in this project, e.g.
# DIAGNOSE_PROMPT: Final[str] = "advice/diagnose"


def get(
    name: str, *, label: str | None = PRODUCTION_LABEL, version: int | None = None
) -> Any:
    """Fetch a prompt version from this component's Langfuse project.

    Pass ``label`` in the request path (always :data:`PRODUCTION_LABEL`) or
    ``version`` from an experiment, so a dataset run is reproducible.
    """
    _ = get_client(COMPONENT)
    raise NotImplementedError
