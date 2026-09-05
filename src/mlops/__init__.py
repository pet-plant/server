"""Evaluation & MLOps (context 7).

ClearML is the authoring / experimentation / comparison store for a small set of
*managed artifacts* — prompts and structured configs the AI contexts run on:

- the ``assessment`` VLM probe prompt,
- the ``advice`` LLM prompt,
- the ``advice`` agent structure,
- the ``knowledge`` probe-generation LLM prompt,
- ...more kinds are added over time (see :mod:`mlops.bundles`).

Each is versioned as a *bundle*. The flow is: author a candidate in ClearML →
:mod:`mlops.evaluation` validates and compares it against the current champion →
:mod:`mlops.promotion` gates it and freezes an approved bundle to a *shipped*
state → the consuming context reads the shipped bundle through
:mod:`mlops.interface`.

Owns the ``mlops`` Postgres schema and the ``eval-sets`` MinIO bucket; reads
``exemplars``.

Public surface:

- :data:`router` — the ``/mlops`` endpoints, mounted by ``main_web`` (once wired).
- :func:`get_active_bundle` — in-process interface: ``kind`` → the currently
  shipped bundle payload, for ``assessment`` / ``advice`` / ``knowledge``.

Nothing here is implemented yet — this package is template scaffolding.
"""

from mlops.api import router
from mlops.interface import get_active_bundle

__all__ = ["get_active_bundle", "router"]
