"""Experiment code for ``registry`` — compare prompt versions.

Owner: TODO

Runs ``runtime.identify_species`` — the production function, with a pinned
prompt version — over a Langfuse dataset, scores each item with ``evaluators``,
and closes a dataset run. Compare runs side by side in the Langfuse UI.

::

    uv run python -m mlops.registry.experiment --version 2 --run-name id-v2
"""

from __future__ import annotations

from typing import Any, Final

from mlops.registry.evaluators import EVALUATORS
from mlops.registry.runtime import identify_species
from mlops.settings import Component

COMPONENT: Final = Component.REGISTRY

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
    _ = (identify_species, EVALUATORS, COMPONENT)
    raise NotImplementedError


def main() -> None:
    """CLI entry point (``python -m mlops.registry.experiment``)."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
