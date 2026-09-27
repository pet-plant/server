"""In-memory SQLite wiring and seed helpers for the ``registry`` tests.

``registry`` checks owners and devices against ``auth`` and species against
``knowledge.species`` through their interfaces, so those tables are created
alongside its own. ``schema_translate_map`` folds all three schemas into
SQLite's default one.
"""

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.db import Base as AuthBase
from core.db import get_session
from core.devices import models as device_models  # noqa: F401 - register tables
from core.devices.dependencies import get_current_device
from core.devices.models import Device
from core.users.dependencies import get_current_active_user
from core.users.models import User
from knowledge import models as knowledge_models  # noqa: F401 - register tables
from knowledge.db import Base as KnowledgeBase
from knowledge.models import Species
from registry import models as registry_models  # noqa: F401 - register tables
from registry.api import router as registry_router
from registry.db import Base as RegistryBase

_BASES: tuple[type[DeclarativeBase], ...] = (AuthBase, KnowledgeBase, RegistryBase)


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    ).execution_options(
        schema_translate_map={"auth": None, "knowledge": None, "registry": None}
    )
    for base in _BASES:
        base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        for base in reversed(_BASES):
            base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def add_user(session_factory: sessionmaker[Session]) -> Callable[..., User]:
    def _add(email: str, *, is_superuser: bool = False) -> User:
        user = User(
            id=uuid.uuid4(),
            email=email,
            name=email.split("@")[0],
            hashed_password="x",
            is_active=True,
            is_superuser=is_superuser,
        )
        with session_factory() as session:
            session.add(user)
            session.commit()
        return user

    return _add


@pytest.fixture
def add_species(session_factory: sessionmaker[Session]) -> Callable[..., None]:
    def _add(*codes: str) -> None:
        with session_factory() as session:
            for code in codes:
                session.add(Species(species_code=code, scientific_name=code.title()))
            session.commit()

    return _add


@pytest.fixture
def add_device(session_factory: sessionmaker[Session]) -> Callable[..., Device]:
    """Insert a device already paired to ``owner`` (skipping the pairing dance)."""

    def _add(owner: User, physical_id: str) -> Device:
        device = Device(id=uuid.uuid4(), physical_id=physical_id, owner_id=owner.id)
        with session_factory() as session:
            session.add(device)
            session.commit()
        return device

    return _add


@pytest.fixture
def alice(add_user: Callable[..., User]) -> User:
    return add_user("alice@example.com")


@pytest.fixture
def bob(add_user: Callable[..., User]) -> User:
    return add_user("bob@example.com")


@pytest.fixture
def admin(add_user: Callable[..., User]) -> User:
    return add_user("ops@example.com", is_superuser=True)


@pytest.fixture
def app(session_factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.include_router(registry_router)

    def _override_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_session
    return app


@pytest.fixture
def client_as(app: FastAPI) -> Iterator[Callable[[User | Device], TestClient]]:
    """``client_as(user_or_device)`` → a test client authenticated as that caller."""
    with TestClient(app) as test_client:

        def _as(caller: User | Device) -> TestClient:
            if isinstance(caller, Device):
                app.dependency_overrides[get_current_device] = lambda: caller
            else:
                app.dependency_overrides[get_current_active_user] = lambda: caller
            return test_client

        yield _as
