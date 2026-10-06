"""``action`` in-process interface tests."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from action import CareEventRead, CareEventType, list_care_events
from action.schemas import ActionCompletedCreate, WateredCreate
from action.service import record_event


def _at(hour: int) -> datetime:
    return datetime(2026, 9, 22, hour, tzinfo=UTC)


def _as_utc(value: datetime) -> datetime:
    """SQLite hands timestamps back naive; they were written as UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _seed(session_factory: sessionmaker[Session], plant_id: uuid.UUID) -> None:
    with session_factory() as session:
        for create in (
            WateredCreate(type=CareEventType.WATERED, occurred_at=_at(10)),
            ActionCompletedCreate(
                type=CareEventType.ACTION_COMPLETED,
                care_plan_id="cp_1",
                action_id="act_a",
                action_type="inspect",
                occurred_at=_at(12),
            ),
            WateredCreate(type=CareEventType.WATERED, occurred_at=_at(8)),  # entered late
        ):
            record_event(session, plant_id, create)


def test_list_care_events(session_factory: sessionmaker[Session]) -> None:
    plant_id, other_plant = uuid.uuid4(), uuid.uuid4()
    _seed(session_factory, plant_id)
    _seed(session_factory, other_plant)

    with session_factory() as session:
        events = list_care_events(session, plant_id)
        assert all(isinstance(e, CareEventRead) for e in events)
        assert all(e.plant_id == plant_id for e in events)
        assert [_as_utc(e.occurred_at) for e in events] == [_at(8), _at(10), _at(12)]
        assert events[-1].action_id == "act_a"

        since = list_care_events(session, plant_id, since=_at(9))
        assert [_as_utc(e.occurred_at) for e in since] == [_at(10), _at(12)]

        watered = list_care_events(session, plant_id, event_types=[CareEventType.WATERED])
        assert [e.event_type for e in watered] == [CareEventType.WATERED] * 2

        latest = list_care_events(session, plant_id, limit=2)  # most recent two, oldest first
        assert [_as_utc(e.occurred_at) for e in latest] == [_at(10), _at(12)]

        assert list_care_events(session, uuid.uuid4()) == []


def test_events_serialise_to_json(session_factory: sessionmaker[Session]) -> None:
    plant_id = uuid.uuid4()
    _seed(session_factory, plant_id)
    with session_factory() as session:
        dumped = list_care_events(session, plant_id)[-1].model_dump(mode="json")
    assert dumped["event_type"] == "action_completed"
    assert dumped["care_plan_id"] == "cp_1"
