"""The pipeline stages, in order, and the functions that call into each context.

Each stage function is the **only** place ``orchestrator`` touches that
context. It receives the identifiers of the work (:class:`StageInput`) — never
another stage's output: every context stores its result in its own schema, and
the next one reads it from there.

A stage function **returns** when its work is stored, and may **raise**
:class:`StageSkipped` when there is nothing to do (e.g. no new frames), which
ends the run without running the later stages.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


class StageSkipped(Exception):  # noqa: N818 - reads as an outcome, not an error
    """Raised by a stage with nothing to do; the message is kept as the reason."""


@dataclass(frozen=True)
class StageInput:
    run_id: uuid.UUID
    plant_id: uuid.UUID
    #: The schedule slot (UTC) the run belongs to.
    scheduled_for: datetime


@dataclass(frozen=True)
class Stage:
    name: str
    fn: Callable[[StageInput], None]


def run_capture(payload: StageInput) -> None:
    """Preprocess the plant's latest capture batch (quality check, segment, align)."""
    # TODO(capture): call the capture context's published function, e.g.
    #   from capture import process_pending_batches
    #   if not process_pending_batches(payload.plant_id, run_id=payload.run_id):
    #       raise StageSkipped("no new frames")
    logger.info("capture stage (stub) plant=%s run=%s", payload.plant_id, payload.run_id)


def run_assessment(payload: StageInput) -> None:
    """Run the probe battery on the VLM and store verdicts."""
    # TODO(assessment): e.g.
    #   from assessment import run_battery
    #   run_battery(payload.plant_id, run_id=payload.run_id)
    logger.info("assessment stage (stub) plant=%s run=%s", payload.plant_id, payload.run_id)


def run_advice(payload: StageInput) -> None:
    """Turn the stored verdicts into a diagnosis and ranked actions."""
    # TODO(advice): e.g.
    #   from advice import generate_for_plant
    #   generate_for_plant(payload.plant_id, run_id=payload.run_id)
    logger.info("advice stage (stub) plant=%s run=%s", payload.plant_id, payload.run_id)


def run_companion(payload: StageInput) -> None:
    """Update the character's mood / utterance from the stored advice."""
    # TODO(companion): e.g.
    #   from companion import update_state
    #   update_state(payload.plant_id, run_id=payload.run_id)
    logger.info("companion stage (stub) plant=%s run=%s", payload.plant_id, payload.run_id)


#: Fixed by the architecture: capture → assessment → advice → companion.
STAGES: tuple[Stage, ...] = (
    Stage("capture", run_capture),
    Stage("assessment", run_assessment),
    Stage("advice", run_advice),
    Stage("companion", run_companion),
)
