"""MLOps for ``knowledge`` — probe generation from research documents.

Owner: TODO · Langfuse project: ``knowledge``

What ``src/knowledge`` imports::

    from mlops.knowledge import GenerateProbesInput, generate_probes

MLOps owns the prompt and its hyper-parameters; ``knowledge`` owns the generated
probes and their approval lifecycle — see :mod:`mlops.knowledge.runtime`.

Self-contained: this package owns its own prompt handling, model calls, tracing,
experiments and scorers. Add modules as the work needs them.
"""

from mlops.knowledge.runtime import (
    GenerateProbesInput,
    GenerateProbesResult,
    generate_probes,
)

__all__ = ["GenerateProbesInput", "GenerateProbesResult", "generate_probes"]
