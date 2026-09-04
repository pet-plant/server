"""Species & Care Knowledge (context 3).

A person researches a species and writes it up as text (`research_document`); that
text is fed to an LLM which produces `metric`s (single-question probes) and their
`metric_action`s. Few-shot exemplar images live in the `exemplars` MinIO bucket.
Owns the `knowledge` Postgres schema.

Public surface:

- :data:`router` — the ``/knowledge`` endpoints (document CRUD + metric
  inspection), mounted by ``main_web``.
- :func:`get_species_metrics` — in-process interface: ``species_code`` →
  current metrics + actions as a JSON-serialisable Pydantic model, for
  ``assessment`` and ``advice``.

The LLM generation logic is not implemented yet.
"""

from knowledge.api import router
from knowledge.interface import get_species_metrics

__all__ = ["get_species_metrics", "router"]
