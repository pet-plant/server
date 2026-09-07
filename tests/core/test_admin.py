"""Bootstrap admin seeding and the ``CurrentSuperuser`` dependency."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from core.db import get_session
from core.security import verify_password
from core.users import CurrentSuperuser, ensure_admin_user
from core.users.api import router as auth_router
from core.users.schemas import UserCreate
from core.users.service import create_user, get_user_by_email

REGISTER = "/auth/register"
TOKEN = "/auth/token"

NON_ADMIN = {"email": "owner@example.com", "name": "Plant Owner", "password": "hunter2hunter"}


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router)

    @app.get("/admin/ping")
    def admin_ping(admin: CurrentSuperuser) -> dict[str, str]:
        return {"email": admin.email}

    def override_get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client


def _token(client: TestClient, email: str, password: str) -> str:
    resp = client.post(TOKEN, data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def test_ensure_admin_user_seeds_a_superuser(session_factory: sessionmaker[Session]) -> None:
    settings = get_settings()
    with session_factory() as session:
        admin = ensure_admin_user(session)

        assert admin.is_superuser is True
        assert admin.is_active is True
        assert admin.email == settings.admin_email.lower()
        assert verify_password(settings.admin_password, admin.hashed_password)


def test_ensure_admin_user_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        first = ensure_admin_user(session)
        second = ensure_admin_user(session)

        assert first.id == second.id


def test_ensure_admin_user_promotes_existing_account(
    session_factory: sessionmaker[Session],
) -> None:
    settings = get_settings()
    with session_factory() as session:
        create_user(
            session,
            UserCreate(
                email=settings.admin_email, name="Someone", password="oldpassword1"
            ),
        )

        ensure_admin_user(session)

        promoted = get_user_by_email(session, settings.admin_email)
        assert promoted is not None
        assert promoted.is_superuser is True
        assert verify_password(settings.admin_password, promoted.hashed_password)


def test_superuser_route_forbidden_for_regular_user(client: TestClient) -> None:
    client.post(REGISTER, json=NON_ADMIN)
    token = _token(client, NON_ADMIN["email"], NON_ADMIN["password"])

    resp = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403


def test_superuser_route_allows_admin(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    settings = get_settings()
    with session_factory() as session:
        ensure_admin_user(session)

    token = _token(client, settings.admin_email, settings.admin_password)
    resp = client.get("/admin/ping", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == settings.admin_email.lower()
