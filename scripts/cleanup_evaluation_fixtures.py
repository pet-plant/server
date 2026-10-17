"""Clean up test fixtures and test run data from the database.

Safely removes only test records (test_* users, postman_tester, test devices,
associated test plants, frames, runs, observations, and care plans)
without affecting baseline catalog species or non-test users.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from action.models import CareEvent
from advice.models import CarePlan, CarePlanAction
from assessment.models import Observation, PlantMilestone, TriggerResultRecord
from capture.models import Capture, ProcessedFrame
from companion.models import MessageRecord
from core.db import SessionLocal
from core.devices.models import Device, DevicePairing
from core.users.models import User
from orchestrator.models import PipelineRun
from registry.models import Plant


def cleanup_fixtures() -> dict[str, int]:
    """Delete all test-scoped records in cascading foreign-key order."""
    session = SessionLocal()
    counts: dict[str, int] = {}
    try:
        # Find test users
        test_users = (
            session.query(User)
            .filter(
                (User.email.like("test_%@example.com"))
                | (User.email == "postman_tester@example.com")
                | (User.email.like("%test%@example.com"))
            )
            .all()
        )
        test_user_ids = [u.id for u in test_users]

        # Find test devices (owned by test users or matching test prefixes)
        test_devices = (
            session.query(Device)
            .filter(
                (Device.owner_id.in_(test_user_ids))
                | (Device.physical_id.like("test_%"))
                | (Device.physical_id.like("mock_%"))
                | (Device.name.like("%Test%"))
                | (Device.name.like("%Eval%"))
            )
            .all()
        )
        test_device_ids = [d.id for d in test_devices]
        test_device_physical_ids = [d.physical_id for d in test_devices]

        # Find test plants (owned by test users or bound to test devices or named Test%)
        test_plants = (
            session.query(Plant)
            .filter(
                (Plant.owner_id.in_(test_user_ids))
                | (Plant.device_id.in_(test_device_physical_ids))
                | (Plant.name.like("Test%"))
            )
            .all()
        )
        test_plant_ids = [p.id for p in test_plants]

        # 1. Companion Message records
        c_msg = (
            session.query(MessageRecord)
            .filter(MessageRecord.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["message_records"] = c_msg

        # 2. Care Plan Actions & Care Plans
        plans = (
            session.query(CarePlan)
            .filter(CarePlan.plant_id.in_(test_plant_ids))
            .all()
        )
        plan_ids = [p.id for p in plans]
        c_act = (
            session.query(CarePlanAction)
            .filter(CarePlanAction.care_plan_pk.in_(plan_ids))
            .delete(synchronize_session=False)
        )
        counts["care_plan_actions"] = c_act

        c_plan = (
            session.query(CarePlan)
            .filter(CarePlan.id.in_(plan_ids))
            .delete(synchronize_session=False)
        )
        counts["care_plans"] = c_plan

        # 3. Action Care Events
        c_evt = (
            session.query(CareEvent)
            .filter(CareEvent.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["care_events"] = c_evt

        # 4. Assessment Observations, Triggers, Milestones
        c_obs = (
            session.query(Observation)
            .filter(Observation.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["observations"] = c_obs

        c_trg = (
            session.query(TriggerResultRecord)
            .filter(TriggerResultRecord.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["trigger_results"] = c_trg

        c_mls = (
            session.query(PlantMilestone)
            .filter(PlantMilestone.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["plant_milestones"] = c_mls

        # 5. Orchestrator Pipeline Runs
        c_runs = (
            session.query(PipelineRun)
            .filter(PipelineRun.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["pipeline_runs"] = c_runs

        # 6. Capture Processed Frames & Raw Captures
        c_pf = (
            session.query(ProcessedFrame)
            .filter(ProcessedFrame.plant_id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["processed_frames"] = c_pf

        c_cap = (
            session.query(Capture)
            .filter(
                (Capture.plant_id.in_(test_plant_ids))
                | (Capture.device_id.in_(test_device_physical_ids))
            )
            .delete(synchronize_session=False)
        )
        counts["captures"] = c_cap

        # 7. Plants
        c_plants = (
            session.query(Plant)
            .filter(Plant.id.in_(test_plant_ids))
            .delete(synchronize_session=False)
        )
        counts["plants"] = c_plants

        # 8. Device Pairings and Devices
        c_dp = (
            session.query(DevicePairing)
            .filter(DevicePairing.device_id.in_(test_device_ids))
            .delete(synchronize_session=False)
        )
        counts["device_pairings"] = c_dp

        c_dev = (
            session.query(Device)
            .filter(Device.id.in_(test_device_ids))
            .delete(synchronize_session=False)
        )
        counts["devices"] = c_dev

        # 9. Test Users (never touch admin / superusers)
        c_usr = (
            session.query(User)
            .filter(User.id.in_(test_user_ids), User.is_superuser.is_(False))
            .delete(synchronize_session=False)
        )
        counts["test_users"] = c_usr

        session.commit()
        return counts
    finally:
        session.close()


if __name__ == "__main__":
    deleted = cleanup_fixtures()
    print("Database test fixtures cleaned up successfully:")
    for k, v in deleted.items():
        if v > 0:
            print(f"  {k}: {v} deleted")
    if not any(deleted.values()):
        print("  (Database was already clean, 0 test records found)")
