"""Scorers for ``advice`` experiments.

Owner: TODO

An evaluator maps one run's output and the dataset item's expected value to a
:class:`Score`, which ``experiment.py`` writes to Langfuse against the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Score:
    """One scored dimension of one output."""

    name: str
    value: float
    comment: str | None = None


# TODO: this component's scorers. Shape:
def example(output: Any, expected: Any) -> Score:
    raise NotImplementedError


#: Applied to every item of a dataset run.
EVALUATORS: list[Any] = []
