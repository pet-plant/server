"""Orchestration (part of context 8): the scheduled pipeline.

At each slot in ``config/orchestrator.toml`` every live plant (from
``registry``) gets a **run**, and the run's stages are called in order —
``capture → assessment → advice → companion``. Each
context stores its own result, so nothing is passed between stages but the
run's identifiers. Owns the ``orchestrator`` schema.

PoC: a stage that raises marks its run ``failed`` and the loop moves on; nothing
is retried.

Public surface:

- :data:`router` — ``/orchestrator`` endpoints (superuser),
  mounted by ``main_web``.
- :class:`OrchestratorLoop` — the background scheduler ``main_web`` starts.
- :func:`tick` — one pass of that loop, callable directly (tests, manual runs).
- :class:`StageInput`, :class:`StageSkipped` — the contract a context's stage
  function is written against.
"""

from orchestrator.api import router
from orchestrator.stages import StageInput, StageSkipped
from orchestrator.worker import OrchestratorLoop, tick

__all__ = ["OrchestratorLoop", "StageInput", "StageSkipped", "router", "tick"]
