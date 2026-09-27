"""Stand-in stages and shared constants for the orchestrator tests.

``PLAN`` scripts what a stage does next: a list of exceptions/``None`` consumed
one call at a time, keyed by ``(stage, plant_id)``. Unscripted calls succeed.
``CALLS`` records every call in order.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from orchestrator.stages import Stage, StageInput
from orchestrator.worker import TickReport

#: 07:05 in Tokyo on 2026-09-27 — five minutes after the first slot.
JST_0705 = datetime(2026, 9, 26, 22, 5, tzinfo=UTC)

RAW_CONFIG: dict[str, Any] = {
    "timezone": "Asia/Tokyo",
    "schedule": ["07:00", "12:00"],
    "catch_up_minutes": 60,
}

#: ``run_tick(now)`` — the conftest fixture of the same name.
RunTick = Callable[[datetime], TickReport]

CALLS: list[tuple[str, uuid.UUID]] = []
PLAN: dict[tuple[str, uuid.UUID], list[BaseException | None]] = {}


def _fake(name: str) -> Callable[[StageInput], None]:
    def stage(payload: StageInput) -> None:
        CALLS.append((name, payload.plant_id))
        script = PLAN.get((name, payload.plant_id))
        if script and (step := script.pop(0)) is not None:
            raise step

    return stage


FAKE_STAGES = tuple(
    Stage(name, _fake(name)) for name in ("capture", "assessment", "advice", "companion")
)
