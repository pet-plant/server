"""MLOps for ``advice`` — diagnosis and ranked care actions.

Owner: TODO · Langfuse project: ``advice``

What ``src/advice`` imports::

    from mlops.advice import AdviceInput, generate_advice

Self-contained: this package owns its own prompt handling, model calls, tracing,
experiments and scorers. Add modules as the work needs them — the agent
structure, if the flow grows into one, belongs here as code.
"""

from mlops.advice.runtime import AdviceInput, AdviceResult, generate_advice

__all__ = ["AdviceInput", "AdviceResult", "generate_advice"]
