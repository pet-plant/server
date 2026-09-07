"""MLOps for ``knowledge`` — probe generation from research documents.

Owner: TODO · Langfuse project: ``knowledge``

What ``src/knowledge`` imports::

    from mlops.knowledge import (
        GenerateProbesInput, generate_probes,   # the agent
        ReviewVerdict, record_review,           # the human verdict, back to Langfuse
    )

MLOps owns the prompt and its hyper-parameters; ``knowledge`` owns the generated
probes and their approval lifecycle — see :mod:`mlops.knowledge.runtime`.

| Module | Holds |
|---|---|
| `schemas.py` | The output contract, and every rule a generated set must satisfy |
| `prompts.py` | The Langfuse prompt names and how a version is fetched |
| `runtime.py` | The agent: generate → validate → repair, then a validated set or an error |
| `review.py` | The human verdict, written back as a Langfuse score |
| `evaluators.py` | Automatic checks — well-formedness only, never quality |
| `experiment.py` | Dataset runs over `runtime`'s own function, with a pinned version |
"""

from mlops.knowledge.review import ReviewVerdict, record_review, trace_url
from mlops.knowledge.runtime import (
    GenerateProbesInput,
    GenerateProbesResult,
    ProbeGenerationError,
    generate_probes,
)
from mlops.knowledge.schemas import (
    GeneratedAction,
    GeneratedProbe,
    GeneratedProbeSet,
    UngroundedProbeError,
)

__all__ = [
    "GenerateProbesInput",
    "GenerateProbesResult",
    "GeneratedAction",
    "GeneratedProbe",
    "GeneratedProbeSet",
    "ProbeGenerationError",
    "ReviewVerdict",
    "UngroundedProbeError",
    "generate_probes",
    "record_review",
    "trace_url",
]
