"""Published in-process interface: ``get_species_probes``."""

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from knowledge.interface import get_species_probes

SeedFn = Callable[..., Any]


def test_returns_none_without_an_approved_set(
    session_factory: sessionmaker[Session], seed_full: SeedFn
) -> None:
    with session_factory() as session:
        seed_full(session, status="draft")
        assert get_species_probes(session, "spath") is None


def test_returns_json_serialisable_bundle(
    session_factory: sessionmaker[Session], seed_full: SeedFn
) -> None:
    with session_factory() as session:
        seed_full(session)
        bundle = get_species_probes(session, "spath")

    assert bundle is not None
    assert bundle.species_code == "spath"
    assert bundle.is_stale is False

    payload = bundle.model_dump(mode="json")
    assert json.loads(json.dumps(payload))  # round-trips as plain JSON
    probe = payload["probes"][0]
    assert probe["care_need"] == "water_deficit"
    assert probe["actions"][0]["expect_max_hours"] == 48
    assert probe["exemplars"][0]["label"] == {"verdict": "worse", "severity": 2}
