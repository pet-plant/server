"""Species & Care Knowledge (context 3).

A person researches a species and writes it up as text (`research_document`); that
text is fed to an LLM which produces `probe`s (single-question probes) and their
`probe_action`s. Few-shot exemplar images live in the `exemplars` MinIO bucket.
Owns the `knowledge` Postgres schema.

Nothing is edited in place: a revised research text is a new row that archives
the old one, and approving another probe set archives the one it replaces, so a
species always has exactly one approved set (and archived sets can be swapped
back in).

Public surface:

- :data:`router` — the ``/knowledge`` endpoints (document authoring + probe
  inspection), mounted by ``main_web``.
- :func:`get_species_probes` — in-process interface: ``species_code`` →
  approved probes + actions as a JSON-serialisable Pydantic model, for
  ``assessment`` and ``advice``.

The LLM generation logic is not implemented yet.
"""

from knowledge.api import router
from knowledge.interface import get_species_probes

__all__ = ["get_species_probes", "router"]
