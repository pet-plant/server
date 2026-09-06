"""MLOps for ``assessment`` — VLM probe execution.

Owner: TODO · Langfuse project: ``assessment``

What ``src/assessment`` imports::

    from mlops.assessment import ProbeInput, run_probe

Self-contained: this package owns its own prompt handling, model calls, tracing,
experiments and scorers. Add modules as the work needs them.
"""

from mlops.assessment.runtime import ProbeInput, ProbeVerdict, run_probe

__all__ = ["ProbeInput", "ProbeVerdict", "run_probe"]
