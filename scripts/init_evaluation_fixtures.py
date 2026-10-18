"""Seed database fixtures required for evaluation and Bruno collection runs.

Creates/ensures:
1. Baseline botanical species catalog (monstera, peace lily, sweet basil).
2. Bootstrap admin user.
3. Dedicated test user (test_evaluator@example.com) and test device pairing.
4. Bound test plant for photo capture and pipeline orchestration.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

# Ensure src/ is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from action.db import init_models as init_action_models
from advice.db import init_models as init_advice_models
from assessment.db import init_models as init_assessment_models
from capture.db import init_models as init_capture_models
from companion.db import init_models as init_companion_models
from core.db import SessionLocal, init_models
from core.devices.models import Device, DevicePairing
from core.security import hash_opaque_token, hash_password
from core.users import ensure_admin_user
from core.users.models import User
from knowledge.db import init_models as init_knowledge_models
from knowledge.models import Species
from orchestrator.db import init_models as init_orchestrator_models
from registry.db import init_models as init_registry_models
from registry.models import Plant

DEFAULT_TEST_EMAIL = "test_evaluator@example.com"
DEFAULT_TEST_PASSWORD = "Password123!"
DEFAULT_DEVICE_ID = "test_device_eval_01"
DEFAULT_DEVICE_TOKEN = "ppd_test_eval_device_secret_token_123"


def init_all_database_models() -> None:
    """Initialize database tables across all contexts."""
    init_models()
    init_knowledge_models()
    init_registry_models()
    init_orchestrator_models()
    init_capture_models()
    init_action_models()
    init_assessment_models()
    init_advice_models()
    init_companion_models()


def setup_fixtures() -> dict[str, str]:
    """Seed baseline catalog and test credentials. Returns dict of seeded IDs."""
    init_all_database_models()

    session = SessionLocal()
    try:
        # 1. Admin user
        ensure_admin_user(session)

        # 2. Species catalogue
        species_catalog = [
            ("monstera_deliciosa", "Monstera deliciosa", "Swiss Cheese Plant"),
            ("spath", "Spathiphyllum wallisii", "Peace Lily"),
            ("ocimum_basilicum", "Ocimum basilicum", "Sweet Basil"),
        ]
        for code, sci_name, com_name in species_catalog:
            existing = session.query(Species).filter(Species.species_code == code).first()
            if not existing:
                session.add(
                    Species(
                        species_code=code,
                        scientific_name=sci_name,
                        common_name=com_name,
                    )
                )
        session.flush()

        # 3. Dedicated test user
        user = session.query(User).filter(User.email == DEFAULT_TEST_EMAIL).first()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=DEFAULT_TEST_EMAIL,
                name="Evaluation Test User",
                hashed_password=hash_password(DEFAULT_TEST_PASSWORD),
                is_active=True,
                is_superuser=False,
            )
            session.add(user)
            session.flush()

        # 4. Test Edge Device
        token_hash = hash_opaque_token(DEFAULT_DEVICE_TOKEN)
        device = session.query(Device).filter(Device.physical_id == DEFAULT_DEVICE_ID).first()
        if not device:
            device = Device(
                id=uuid.uuid4(),
                physical_id=DEFAULT_DEVICE_ID,
                owner_id=user.id,
                name="Evaluation Planter Device",
                status="active",
                token_hash=token_hash,
            )
            session.add(device)
            session.flush()
        else:
            device.owner_id = user.id
            device.token_hash = token_hash
            device.status = "active"
            session.flush()

        # 5. Test Plant bound to Device
        plant = session.query(Plant).filter(Plant.device_id == device.physical_id).first()
        if not plant:
            plant = Plant(
                id=uuid.uuid4(),
                owner_id=user.id,
                device_id=device.physical_id,
                name="Test Evaluator Monstera",
                species_code="monstera_deliciosa",
                note="Evaluation test plant",
            )
            session.add(plant)
            session.flush()

        session.commit()

        result = {
            "user_id": str(user.id),
            "user_email": user.email,
            "user_password": DEFAULT_TEST_PASSWORD,
            "device_id": str(device.id),
            "device_physical_id": device.physical_id,
            "device_token": DEFAULT_DEVICE_TOKEN,
            "plant_id": str(plant.id),
            "species_code": plant.species_code,
        }
        return result
    finally:
        session.close()


if __name__ == "__main__":
    seeded = setup_fixtures()
    print("Database fixtures successfully initialized:")
    for k, v in seeded.items():
        print(f"  {k}: {v}")
