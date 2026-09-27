"""``/orchestrator`` API."""

import uuid
from collections.abc import Iterator

import orchestrator_fakes as fakes
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from orchestrator_fakes import JST_0705, RunTick
from sqlalchemy.orm import Session, sessionmaker

from core.db import get_session
from core.users.dependencies import get_current_active_user
from core.users.models import User
from orchestrator.api import router
from registry.models import Plant


def _user(*, superuser: bool) -> User:
    return User(
        id=uuid.uuid4(),
        email="ops@example.com" if superuser else "owner@example.com",
        name="x",
        hashed_password="x",
        is_active=True,
        is_superuser=superuser,
    )


@pytest.fixture
def app(session_factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    def _override_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_active_user] = lambda: _user(superuser=True)
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_superuser_only(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[get_current_active_user] = lambda: _user(superuser=False)
    assert client.get("/orchestrator/runs").status_code == 403
    assert client.get("/orchestrator/schedule").status_code == 403


def test_list_filter_and_detail(
    client: TestClient, run_tick: RunTick, plants: list[uuid.UUID]
) -> None:
    fakes.PLAN[("advice", plants[0])] = [RuntimeError("LLM down")]
    run_tick(JST_0705)

    runs = client.get("/orchestrator/runs").json()
    assert {r["status"] for r in runs} == {"failed", "succeeded"}

    failed = client.get("/orchestrator/runs", params={"status": "failed"}).json()
    assert len(failed) == 1
    run = client.get(f"/orchestrator/runs/{failed[0]['id']}").json()
    assert run["plant_id"] == str(plants[0])
    assert run["current_stage"] == "advice"
    assert "LLM down" in run["detail"]

    by_plant = client.get("/orchestrator/runs", params={"plant_id": str(plants[1])}).json()
    assert [r["status"] for r in by_plant] == ["succeeded"]

    assert client.get(f"/orchestrator/runs/{uuid.uuid4()}").status_code == 404


def test_manual_run(client: TestClient, session_factory: sessionmaker[Session]) -> None:
    plant_id = uuid.uuid4()
    with session_factory() as session:
        session.add(Plant(id=plant_id, owner_id=uuid.uuid4(), name="a"))
        session.commit()

    created = client.post("/orchestrator/runs", json={"plant_id": str(plant_id)})
    assert created.status_code == 201
    assert created.json()["trigger"] == "manual"
    assert created.json()["status"] == "queued"
    assert created.json()["current_stage"] == "capture"

    unknown = client.post("/orchestrator/runs", json={"plant_id": str(uuid.uuid4())})
    assert unknown.status_code == 404


def test_schedule(client: TestClient) -> None:
    schedule = client.get("/orchestrator/schedule").json()
    assert schedule["timezone"] == "Asia/Tokyo"
    assert schedule["next_slot"] is not None
    assert schedule["stages"] == ["capture", "assessment", "advice", "companion"]
