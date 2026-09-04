"""ORM models for the ``knowledge`` schema.

Importing this package registers every table on
:data:`knowledge.db.Base.metadata`.

Chain of ownership::

    species
      └── research_document      human-written research text (the LLM input)
            └── metric_set       one LLM generation run (+ human approval)
                  └── metric     one single-question probe
                        ├── metric_action     what to do when it fires
                        └── metric_exemplar   few-shot image (bytes in MinIO)
"""

from knowledge.models.action import MetricAction
from knowledge.models.document import ResearchDocument
from knowledge.models.exemplar import MetricExemplar
from knowledge.models.metric import Metric, MetricSet
from knowledge.models.species import Species

__all__ = [
    "Metric",
    "MetricAction",
    "MetricExemplar",
    "MetricSet",
    "ResearchDocument",
    "Species",
]
