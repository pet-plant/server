"""Experiment for agent v1 — publish the prompts on disk, then run them.

Owner: TODO

::

    uv run python -m mlops.knowledge.agents.v1.experiment --run-name v1-tighter-guard

**Rewrite this file freely.** It is the bench, and every experiment asks a
different question: a different dataset, a different comparison, a sweep over a
hyper-parameter. Only one rule survives the rewriting — **the task must call
``AGENT.run``**. An experiment that reimplements the agent stops predicting
production, which is the only reason to run a bench at all.

## What one run does

1. **Publish** the prompt files under ``prompts/`` and the dataset file under
   ``data/knowledge/`` to Langfuse. Prompt versions arrive unlabelled —
   publishing never deploys — and unchanged prompts are not republished, so
   version numbers count decisions rather than invocations.
2. **Run** the dataset against those exact prompt versions, pinned by number
   rather than by a moving label, so the run stays reproducible afterwards.
3. **Score** each item for well-formedness and close the dataset run.

Then read the run in Langfuse and judge the probes yourself — no automatic score
can — and move the ``production`` label when you are satisfied.

Dataset items are one research document each and live in
``data/knowledge/<dataset>.toml`` — see :mod:`mlops.knowledge.datasets`. There is
no expected output: nobody can write the one correct probe set for a document,
and pretending otherwise is how a meaningless metric gets born.
"""

from __future__ import annotations

import argparse
import logging
from typing import Any, Final

from mlops.client import LangfuseNotConfiguredError, flush, get_client
from mlops.knowledge import datasets, publishing
from mlops.knowledge.agents.v1.agent import AGENT, VERSION
from mlops.knowledge.contract import GenerateProbesInput
from mlops.knowledge.evaluators import EVALUATORS
from mlops.settings import Component

logger = logging.getLogger(__name__)

COMPONENT: Final = Component.KNOWLEDGE

#: Langfuse dataset backing this experiment. The file is
#: ``data/knowledge/research-documents.toml``; ``--dataset`` picks another.
DATASET: Final[str] = "research-documents"


def _task(
    *, item: Any, pins: dict[str, int], overrides: dict[str, Any] | None
) -> Any:
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
        return AGENT.run(payload, pins=pins, overrides=overrides)
    except Exception:
        logger.warning("Generation failed for %s", payload.species_code, exc_info=True)
        return None


def run_experiment(
    *,
    run_name: str,
    dataset_name: str = DATASET,
    overrides: dict[str, Any] | None = None,
    commit_message: str | None = None,
) -> Any:
    """Publish this version's prompts, then score them over the dataset.

    ``run_name`` is the column label in the Langfuse comparison view, so make it
    identify the variable under test — ``tighter-not-this``, not ``run-3``.
    """
    pins = publishing.sync(AGENT, commit_message=commit_message or run_name)
    published = datasets.sync(dataset_name)
    logger.info(
        "Running %s (%d items) against %s",
        published.name,
        len(published.items),
        publishing.describe(pins),
    )

    dataset = get_client(COMPONENT).get_dataset(dataset_name)
    # Through the dataset, not the client: that is what ties the run to the
    # dataset and its version, so it lands in the Runs tab where two candidates
    # can be put side by side.
    result = dataset.run_experiment(
        name=dataset_name,
        run_name=run_name,
        description=f"agent {VERSION} · {publishing.describe(pins)}",
        task=lambda *, item, **_: _task(item=item, pins=pins, overrides=overrides),
        evaluators=EVALUATORS,
        # The pinned versions, so the run says what it ran even after the
        # prompt files move on.
        metadata={"agent_version": VERSION, "prompts": publishing.describe(pins)},
    )
    # Tracing is asynchronous and a CLI run exits immediately: without this the
    # traces the run just produced never reach Langfuse.
    flush(COMPONENT)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Publish agent v1's prompt files to Langfuse and score them over the "
            "dataset. Publishing never deploys — promote in the Langfuse UI."
        )
    )
    parser.add_argument(
        "--run-name", required=True, help="column label in the Langfuse comparison view"
    )
    parser.add_argument(
        "--dataset",
        default=DATASET,
        choices=datasets.available() or None,
        help="a file stem in data/knowledge/",
    )
    parser.add_argument(
        "--message", default=None, help="commit message for the prompt version"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        result = run_experiment(
            run_name=args.run_name,
            dataset_name=args.dataset,
            commit_message=args.message,
        )
    except LangfuseNotConfiguredError as exc:
        # A missing key pair is a setup mistake, not a bug: say what to set
        # rather than printing a traceback at someone.
        raise SystemExit(str(exc)) from None

    print(result.format())  # noqa: T201 - a CLI is allowed to print
    if result.dataset_run_url:
        # The automatic scores are only half the picture: open this and read the
        # probe sets. Whether they are *right* is not in the numbers above.
        print(f"\nReview, then promote in Langfuse: {result.dataset_run_url}")  # noqa: T201


if __name__ == "__main__":
    main()
