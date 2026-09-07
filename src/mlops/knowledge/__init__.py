"""MLOps for ``knowledge`` — probe generation from research documents.

Owner: TODO · Langfuse project: ``knowledge``

What ``src/knowledge`` imports::

    from mlops.knowledge import GenerateProbesInput, get_agent
    from mlops.knowledge import ReviewVerdict, record_review

    result = get_agent().run(GenerateProbesInput(...))

MLOps owns the prompt and how the model is asked; ``knowledge`` owns the
generated probes and their approval lifecycle.

| Module | Holds |
|---|---|
| `contract.py` | The I/O types and the `ProbeAgent` protocol every version implements |
| `schemas.py` | The output contract, and every rule a generated set must satisfy |
| `registry.py` | Which agent versions exist; `get_agent(version)` |
| `agents/<v>/` | One interchangeable implementation, with its own prompts and bench |
| `publishing.py` | Prompt files → Langfuse versions, idempotently, never deployed |
| `evaluators.py` | Automatic checks — well-formedness only, never quality |
| `review.py` | The human verdict, written back as a Langfuse score |

**Prompt text lives in this repository**, under `agents/<version>/prompts/`, and
is published from there. Langfuse holds the version registry, the traces and
runs, the human scores, and the `production` label that decides what is live.
Promotion is a label move in the Langfuse UI; the text itself is not edited there.
"""

from mlops.knowledge.contract import (
    GenerateProbesInput,
    GenerateProbesResult,
    ProbeAgent,
    ProbeGenerationError,
    PromptRef,
)
from mlops.knowledge.registry import AGENTS, DEFAULT_VERSION, get_agent
from mlops.knowledge.review import ReviewVerdict, record_review, trace_url
from mlops.knowledge.schemas import (
    GeneratedAction,
    GeneratedProbe,
    GeneratedProbeSet,
    UngroundedProbeError,
)

__all__ = [
    "AGENTS",
    "DEFAULT_VERSION",
    "GenerateProbesInput",
    "GenerateProbesResult",
    "GeneratedAction",
    "GeneratedProbe",
    "GeneratedProbeSet",
    "ProbeAgent",
    "ProbeGenerationError",
    "PromptRef",
    "ReviewVerdict",
    "UngroundedProbeError",
    "get_agent",
    "record_review",
    "trace_url",
]
