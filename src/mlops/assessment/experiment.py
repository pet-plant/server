"""Experiment code for ``assessment`` — compare prompt versions.

Owner: TODO

Runs ``runtime.run_probe`` — the production function, with a pinned prompt
version — over a Langfuse dataset, scores each item with ``evaluators``, and
closes a dataset run. Compare runs side by side in the Langfuse UI.

::

    uv run python -m mlops.assessment.experiment --version 7 --run-name probe-v7
"""

from __future__ import annotations

from typing import Any, Final

from mlops.assessment.evaluators import EVALUATORS
from mlops.assessment.runtime import run_probe
from mlops.settings import Component

COMPONENT: Final = Component.ASSESSMENT

#: Langfuse dataset backing this experiment. Items are authored in the Langfuse
#: UI, not in this repository.
DATASET: Final[str] = ""  # TODO


def run_experiment(
    *,
    run_name: str,
    version: int | None = None,
    dataset_name: str = DATASET,
    overrides: dict[str, Any] | None = None,
) -> Any:
    """Score one prompt version over the dataset as a Langfuse dataset run.

    ``run_name`` is the column label in the Langfuse comparison view, so make it
    identify the variable under test.
    """
    _ = (run_probe, EVALUATORS, COMPONENT)
    raise NotImplementedError


def main() -> None:
    """CLI entry point (``python -m mlops.assessment.experiment``)."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
