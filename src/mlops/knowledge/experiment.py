"""Experiment code for ``knowledge`` — compare prompt versions.

Owner: TODO

Runs ``runtime.generate_probes`` — the production function, with a pinned prompt
version — over a Langfuse dataset, attaches the automatic checks from
``evaluators``, and closes a dataset run. Compare runs side by side in the
Langfuse UI.

::

    uv run python -m mlops.knowledge.experiment --version 4 --run-name gen-v4

**A run is only half an experiment.** The automatic scores say whether the
output was well-formed; they cannot say whether the probes are right. After a
run finishes, open it in Langfuse and judge the sets by hand — the verdict is
written under the same score name the ``knowledge`` review API uses
(:data:`~mlops.knowledge.review.REVIEW_SCORE`), so bench review and production
review aggregate into one column.

Dataset items are authored in the Langfuse UI. One item = one research document:

.. code-block:: json

    {
      "input": {
        "species_code": "spath",
        "scientific_name": "Spathiphyllum wallisii",
        "common_name": "Peace lily",
        "document_title": "watering and light",
        "document_body": "…the research text, verbatim…"
      }
    }

There is no ``expected_output``: nobody can write the one correct probe set for
a document, and pretending otherwise is how a meaningless metric gets born.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Final

from mlops.client import LangfuseNotConfiguredError, flush, get_client
from mlops.knowledge.evaluators import EVALUATORS
from mlops.knowledge.runtime import GenerateProbesInput, generate_probes
from mlops.settings import Component

logger = logging.getLogger(__name__)

COMPONENT: Final = Component.KNOWLEDGE

#: Langfuse dataset backing this experiment. Items are authored in the Langfuse
#: UI, not in this repository.
DATASET: Final[str] = "knowledge-research-documents"


def _task(*, item: Any, version: int | None, overrides: dict[str, Any] | None) -> Any:
    """Run one dataset item through the production code path.

    Returning ``None`` on failure rather than raising keeps one bad document
    from ending the run — ``validation_passed`` records it as a zero and the
    other items still get scored.
    """
    data = item.input if hasattr(item, "input") else item["input"]
    payload = GenerateProbesInput(
        species_code=data["species_code"],
        scientific_name=data["scientific_name"],
        common_name=data.get("common_name"),
        document_title=data["document_title"],
        document_body=data["document_body"],
    )
    try:
        return generate_probes(payload, version=version, overrides=overrides)
    except Exception:
        logger.warning(
            "Generation failed for %s", payload.species_code, exc_info=True
        )
        return None


def run_experiment(
    *,
    run_name: str,
    version: int | None = None,
    dataset_name: str = DATASET,
    overrides: dict[str, Any] | None = None,
) -> Any:
    """Score one prompt version over the dataset as a Langfuse dataset run.

    ``run_name`` is the column label in the Langfuse comparison view, so make it
    identify the variable under test — ``v4-lower-temp``, not ``run-3``.
    """
    dataset = get_client(COMPONENT).get_dataset(dataset_name)
    # Run it through the dataset rather than the client: that is what ties the
    # run to the dataset (and its version), so it lands in the dataset's Runs
    # tab where two prompt versions can be put side by side.
    result = dataset.run_experiment(
        name=dataset_name,
        run_name=run_name,
        description=(
            f"generate-probes prompt v{version}"
            if version
            else "generate-probes prompt at the production label"
        ),
        task=lambda *, item, **_: _task(
            item=item, version=version, overrides=overrides
        ),
        evaluators=EVALUATORS,
        metadata={"prompt_version": str(version) if version else "production"},
    )
    # Tracing is asynchronous and a CLI run exits immediately: without this the
    # traces the run just produced never reach Langfuse.
    flush(COMPONENT)
    return result


def main() -> None:
    """CLI entry point (``python -m mlops.knowledge.experiment``)."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the probe-generation prompt over the Langfuse dataset as a "
            "dataset run, then review the results by hand in Langfuse."
        )
    )
    parser.add_argument(
        "--run-name", required=True, help="column label in the Langfuse comparison view"
    )
    parser.add_argument(
        "--version",
        type=int,
        default=None,
        help="prompt version to pin; omit to run whatever `production` points at",
    )
    parser.add_argument("--dataset", default=DATASET)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    try:
        result = run_experiment(
            run_name=args.run_name, version=args.version, dataset_name=args.dataset
        )
    except LangfuseNotConfiguredError as exc:
        # A missing key pair is a setup mistake, not a bug: say what to set
        # rather than printing a traceback at someone.
        raise SystemExit(str(exc)) from None
    # noqa: T201 below — a CLI is allowed to print.
    print(result.format())  # noqa: T201
    if result.dataset_run_url:
        # The automatic scores are only half the picture: open this and read the
        # probe sets. Whether they are *right* is not in the numbers above.
        print(f"\nReview the run: {result.dataset_run_url}")  # noqa: T201


if __name__ == "__main__":
    main()
