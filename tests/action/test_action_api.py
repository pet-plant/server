"""``/action`` HTTP API tests."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from action.models import CareEvent
from core.devices.models import Device
from core.users.models import User
from registry.models import Plant

ClientAs = Callable[[User | Device], TestClient]
MISSING = "00000000-0000-0000-0000-000000000000"

COMPLETED = {
    "type": "action_completed",
    "care_plan_id": "cp_a7b8c9d0e1f2",
    "action_id": "act_8e4b1a2c",
    "action_type": "water",
}


def _events(session_factory: sessionmaker[Session]) -> list[CareEvent]:
    with session_factory() as session:
        return list(session.scalars(select(CareEvent)).all())


def test_owner_records_completed_action(
    client_as: ClientAs,
    alice: User,
    add_plant: Callable[..., Plant],
    session_factory: sessionmaker[Session],
) -> None:
    plant = add_plant(alice)
    res = client_as(alice).post(f"/action/plants/{plant.id}/events", json=COMPLETED)
    assert res.status_code == 201
    body = res.json()
    assert body["plant_id"] == str(plant.id)
    assert body["event_type"] == "action_completed"
    assert body["care_plan_id"] == "cp_a7b8c9d0e1f2"
    assert body["action_id"] == "act_8e4b1a2c"
    assert body["action_type"] == "water"
    assert body["recorded_by_user_id"] == str(alice.id)
    assert body["recorded_by_device_id"] is None
    assert len(_events(session_factory)) == 1


def test_watering_without_and_with_care_plan(
    client_as: ClientAs, alice: User, add_plant: Callable[..., Plant]
) -> None:
    plant = add_plant(alice)
    client = client_as(alice)
    url = f"/action/plants/{plant.id}/events"

    plain = client.post(url, json={"type": "watered", "details": {"amount_ml": 200}})
    assert plain.status_code == 201
    assert plain.json()["event_type"] == "watered"
    assert plain.json()["care_plan_id"] is None
    assert plain.json()["action_id"] is None
    assert plain.json()["details"] == {"amount_ml": 200}

    from_card = client.post(url, json={"type": "watered", "care_plan_id": "cp_1"})
    assert from_card.status_code == 201
    assert from_card.json()["care_plan_id"] == "cp_1"


def test_occurred_at(client_as: ClientAs, alice: User, add_plant: Callable[..., Plant]) -> None:
    plant = add_plant(alice)
    client = client_as(alice)
    url = f"/action/plants/{plant.id}/events"

    earlier = datetime(2026, 9, 22, 8, 30, tzinfo=UTC)
    res = client.post(url, json={"type": "watered", "occurred_at": earlier.isoformat()})
    assert res.status_code == 201
    assert datetime.fromisoformat(res.json()["occurred_at"]).replace(tzinfo=UTC) == earlier

    future = datetime.now(UTC) + timedelta(hours=1)
    res = client.post(url, json={"type": "watered", "occurred_at": future.isoformat()})
    assert res.status_code == 422

    # naive timestamps are ambiguous
    res = client.post(url, json={"type": "watered", "occurred_at": "2026-09-22T08:30:00"})
    assert res.status_code == 422


def test_client_event_id_deduplicates(
    client_as: ClientAs,
    alice: User,
    add_plant: Callable[..., Plant],
    session_factory: sessionmaker[Session],
) -> None:
    plant = add_plant(alice)
    client = client_as(alice)
    url = f"/action/plants/{plant.id}/events"
    payload = {**COMPLETED, "client_event_id": "press-1"}

    first = client.post(url, json=payload)
    again = client.post(url, json=payload)
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    assert len(_events(session_factory)) == 1

    other = client.post(url, json={**payload, "client_event_id": "press-2"})
    assert other.status_code == 201
    assert len(_events(session_factory)) == 2


def test_invalid_bodies(client_as: ClientAs, alice: User, add_plant: Callable[..., Plant]) -> None:
    plant = add_plant(alice)
    client = client_as(alice)
    url = f"/action/plants/{plant.id}/events"

    assert client.post(url, json={"type": "unknown"}).status_code == 422
    # a completed action needs the plan and the action it belongs to
    assert client.post(url, json={"type": "action_completed"}).status_code == 422
    assert client.post(url, json={**COMPLETED, "action_type": "dance"}).status_code == 422


def test_plant_access(
    client_as: ClientAs,
    alice: User,
    bob: User,
    add_user: Callable[..., User],
    add_plant: Callable[..., Plant],
) -> None:
    plant = add_plant(alice)
    url = f"/action/plants/{plant.id}/events"

    assert client_as(bob).post(url, json=COMPLETED).status_code == 404
    missing = client_as(alice).post(f"/action/plants/{MISSING}/events", json=COMPLETED)
    assert missing.status_code == 404

    admin = add_user("ops@example.com", is_superuser=True)
    assert client_as(admin).post(url, json=COMPLETED).status_code == 201

    archived = add_plant(alice, archived=True)
    res = client_as(alice).post(f"/action/plants/{archived.id}/events", json=COMPLETED)
    assert res.status_code == 409


def test_device_records_for_its_plant(
    client_as: ClientAs,
    alice: User,
    add_plant: Callable[..., Plant],
    add_device: Callable[..., Device],
) -> None:
    device = add_device(alice, "dev-1")
    plant = add_plant(alice, device_id="dev-1")

    res = client_as(device).post("/action/devices/me/events", json={"type": "watered"})
    assert res.status_code == 201
    assert res.json()["plant_id"] == str(plant.id)
    assert res.json()["recorded_by_device_id"] == str(device.id)
    assert res.json()["recorded_by_user_id"] is None


def test_unbound_device_gets_404(
    client_as: ClientAs, alice: User, add_device: Callable[..., Device]
) -> None:
    device = add_device(alice, "dev-1")
    res = client_as(device).post("/action/devices/me/events", json={"type": "watered"})
    assert res.status_code == 404


def _at(hour: int) -> str:
    return datetime(2026, 9, 22, hour, tzinfo=UTC).isoformat()


def _as_utc(value: str) -> datetime:
    """SQLite hands timestamps back naive; they were written as UTC."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def test_care_plan_progress(
    client_as: ClientAs, alice: User, add_plant: Callable[..., Plant]
) -> None:
    plant = add_plant(alice)
    client = client_as(alice)
    events = f"/action/plants/{plant.id}/events"
    progress = f"/action/plants/{plant.id}/care-plans/cp_1/progress"

    empty = client.get(progress)
    assert empty.status_code == 200
    assert empty.json() == {
        "plant_id": str(plant.id),
        "care_plan_id": "cp_1",
        "completed_actions": [],
        "last_watered_at": None,
    }

    def complete(action_id: str, hour: int, care_plan_id: str = "cp_1") -> None:
        res = client.post(
            events,
            json={
                "type": "action_completed",
                "care_plan_id": care_plan_id,
                "action_id": action_id,
                "action_type": "inspect",
                "occurred_at": _at(hour),
            },
        )
        assert res.status_code == 201

    complete("act_b", 9)
    complete("act_a", 10)
    complete("act_b", 11)  # pressed again: still counts once, at its first time
    complete("act_c", 12, care_plan_id="cp_other")  # another plan
    client.post(events, json={"type": "watered", "occurred_at": _at(8)})
    client.post(events, json={"type": "watered", "occurred_at": _at(7)})  # entered late

    body = client.get(progress).json()
    done = body["completed_actions"]
    assert [a["action_id"] for a in done] == ["act_b", "act_a"]
    assert _as_utc(done[0]["completed_at"]) == datetime.fromisoformat(_at(9))
    assert done[0]["action_type"] == "inspect"
    assert _as_utc(body["last_watered_at"]) == datetime.fromisoformat(_at(8))


def test_care_plan_progress_access(
    client_as: ClientAs, alice: User, bob: User, add_plant: Callable[..., Plant]
) -> None:
    plant = add_plant(alice)
    assert (
        client_as(bob).get(f"/action/plants/{plant.id}/care-plans/cp_1/progress").status_code == 404
    )
    missing = client_as(alice).get(f"/action/plants/{MISSING}/care-plans/cp_1/progress")
    assert missing.status_code == 404

    # an archived plant's history stays readable
    archived = add_plant(alice, archived=True)
    res = client_as(alice).get(f"/action/plants/{archived.id}/care-plans/cp_1/progress")
    assert res.status_code == 200


def test_device_care_plan_progress(
    client_as: ClientAs,
    alice: User,
    add_plant: Callable[..., Plant],
    add_device: Callable[..., Device],
) -> None:
    device = add_device(alice, "dev-1")
    unbound = client_as(device).get("/action/devices/me/care-plans/cp_1/progress")
    assert unbound.status_code == 404

    plant = add_plant(alice, device_id="dev-1")
    client = client_as(device)
    client.post("/action/devices/me/events", json=COMPLETED)
    body = client.get(f"/action/devices/me/care-plans/{COMPLETED['care_plan_id']}/progress").json()
    assert body["plant_id"] == str(plant.id)
    assert [a["action_id"] for a in body["completed_actions"]] == [COMPLETED["action_id"]]
