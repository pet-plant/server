"""In-memory SQLite wiring, a test config and the fake stages for ``orchestrator``."""

import uuid
from collections.abc import Iterator
from datetime import datetime

import orchestrator_fakes as fakes
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from orchestrator import models  # noqa: F401 - register tables
from orchestrator.config import OrchestratorConfig, parse_config
from orchestrator.db import Base
from orchestrator.worker import TickReport, tick
from registry import models as registry_models  # noqa: F401 - register tables
from registry.db import Base as RegistryBase


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    ).execution_options(schema_translate_map={"orchestrator": None, "registry": None})
    # registry's table too: the operations API checks plants through its interface.
    for base in (Base, RegistryBase):
        base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        for base in (Base, RegistryBase):
            base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def config() -> OrchestratorConfig:
    return parse_config(fakes.RAW_CONFIG)


@pytest.fixture(autouse=True)
def _reset_fakes() -> Iterator[None]:
    fakes.CALLS.clear()
    fakes.PLAN.clear()
    yield
    fakes.CALLS.clear()
    fakes.PLAN.clear()


@pytest.fixture
def plants() -> list[uuid.UUID]:
    """Two live plants, in the order ``registry`` would list them."""
    return [uuid.uuid4(), uuid.uuid4()]


@pytest.fixture
def run_tick(
    session_factory: sessionmaker[Session], config: OrchestratorConfig, plants: list[uuid.UUID]
) -> fakes.RunTick:
    """``run_tick(now)`` → one tick at that instant, over ``plants``, with fake stages."""

    def _tick(now: datetime) -> TickReport:
        return tick(
            session_factory,
            config,
            now=lambda: now,
            plant_ids=lambda _session: plants,
            stages=fakes.FAKE_STAGES,
        )

    return _tick
