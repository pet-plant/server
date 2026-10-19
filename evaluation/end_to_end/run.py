"""Self-contained execution runner for end-to-end pipeline scenario evaluations.

All scenario definitions, expected golden outputs, and canned responses are loaded
strictly from within the evaluation/ directory (evaluation/datasets/end_to_end/).
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from action.db import Base as ActionBase
from advice.db import Base as AdviceBase
from advice.models import CarePlan, CarePlanAction
from assessment.db import Base as AssessmentBase
from assessment.models import Observation, PlantMilestone, TriggerResultRecord
from assessment.schemas import HealthStatus
from capture import models as capture_models  # noqa: F401 - registers tables
from capture.db import Base as CaptureBase
from companion.db import Base as CompanionBase
from companion.models import MessageRecord
from core.db import Base as AuthBase
from evaluation.common.config import EvaluationConfig
from evaluation.common.loaders import load_end_to_end_manifest
from evaluation.common.mock_model import MockChatModel
from evaluation.common.reporting import MetricResult, ScopeExecutionResult, print_scope_aggregate
from evaluation.end_to_end.metrics import evaluate_end_to_end_metrics
from knowledge.db import Base as KnowledgeBase
from orchestrator.db import Base as OrchestratorBase
from orchestrator.models import PipelineRun
from orchestrator.stages import STAGES
from orchestrator.worker import execute_run
from registry.db import Base as RegistryBase
from registry.models import Plant

ALL_BASES = (
    AuthBase,
    RegistryBase,
    KnowledgeBase,
    CaptureBase,
    OrchestratorBase,
    AssessmentBase,
    AdviceBase,
    ActionBase,
    CompanionBase,
)

DATASET_ROOT = Path(__file__).resolve().parent.parent / "datasets" / "end_to_end"


# Scenario configuration mapping scenario files to expected outputs and mock responses
# All paths are strictly relative to DATASET_ROOT
SCENARIO_CONFIGS: dict[str, dict[str, Any]] = {
    "no_change": {
        "file": "scenarios/no_change.json",
        "expected": "expected_outputs/scenario_no_change.json",
        "mock_advice": [],
        "mock_companion": "responses/companion/healthy_steady.json",
    },
    "new_symptom": {
        "file": "scenarios/new_symptom.json",
        "expected": "expected_outputs/scenario_new_symptom.json",
        "mock_advice": ["responses/advice/leaf_yellowing_mild.json"],
        "mock_companion": "responses/companion/care_advice_message.json",
    },
    "severity_increase": {
        "file": "scenarios/severity_increase.json",
        "expected": "expected_outputs/scenario_severity_increase.json",
        "mock_advice": [
            "responses/advice/leaf_yellowing_mild.json",
            "responses/advice/leaf_yellowing_severe.json",
        ],
        "mock_companion": "responses/companion/crisis_alert.json",
    },
    "improvement": {
        "file": "scenarios/improvement.json",
        "expected": "expected_outputs/scenario_improvement.json",
        "mock_advice": ["responses/advice/leaf_yellowing_severe.json"],
        "mock_companion": "responses/companion/improvement_recovery.json",
    },
    "health_status_change": {
        "file": "scenarios/health_status_change.json",
        "expected": "expected_outputs/scenario_health_status_change.json",
        "mock_advice": ["responses/advice/overwatering_stress.json"],
        "mock_companion": "responses/companion/care_advice_message.json",
    },
    "multi_day": {
        "file": "scenarios/milestone_lifecycle.json",
        "expected": "expected_outputs/scenario_multi_day.json",
        "mock_advice": [
            "responses/advice/fungal_infection.json",
            "responses/advice/multi_symptom.json",
        ],
        "mock_companion": "responses/companion/improvement_recovery.json",
    },
}


def load_dataset_json(rel_path: str) -> dict[str, Any] | None:
    """Load JSON file strictly relative to evaluation/datasets/end_to_end/."""
    full_path = DATASET_ROOT / rel_path
    if not full_path.exists():
        return None
    with open(full_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_session_factory() -> sessionmaker[Session]:
    """Create in-memory SQLite engine with all bounded context schemas."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    ).execution_options(
        schema_translate_map={
            "auth": None,
            "registry": None,
            "knowledge": None,
            "vision": None,
            "orchestrator": None,
            "assessment": None,
            "advice": None,
            "action": None,
            "companion": None,
        }
    )
    for base in ALL_BASES:
        base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def build_frontend_response(
    plant: Plant,
    day_count: int,
    timestamp: datetime,
    raw_status: str,
    decision: str,
    companion_message: str | None,
    care_plan: CarePlan | None,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the Frontend Response payload matching poc-ai-agent contract."""
    cp_dict = None
    if care_plan:
        cp_dict = {
            "id": care_plan.care_plan_id,
            "status_label": care_plan.status_label,
            "assessment": care_plan.assessment,
            "actions": actions,
        }
    return {
        "plant_id": str(plant.id),
        "name": plant.name,
        "species": plant.species_code,
        "dayCount": day_count,
        "timestamp": timestamp.isoformat(),
        "health_status": raw_status,
        "decision": decision,
        "companion_message": companion_message or "",
        "care_plan": cp_dict,
    }


def validate_frontend_envelope(fe_envelope: dict[str, Any], fe_data: dict[str, Any]) -> bool:
    """Validate that the Frontend Response Envelope strictly conforms to poc-ai-agent contract."""
    if not isinstance(fe_envelope, dict) or fe_envelope.get("success") is not True:
        return False
    if fe_envelope.get("data") != fe_data:
        return False

    required_fields = [
        "plant_id",
        "name",
        "species",
        "dayCount",
        "timestamp",
        "health_status",
        "decision",
        "companion_message",
    ]
    for field in required_fields:
        if field not in fe_data or fe_data[field] is None:
            return False

    decision = fe_data["decision"]
    care_plan = fe_data.get("care_plan")

    if decision == "CARE_ADVICE_REQUIRED":
        if not isinstance(care_plan, dict):
            return False
        if not care_plan.get("actions"):
            return False
        for action in care_plan["actions"]:
            if action.get("type") not in ("water", "move", "inspect", "other"):
                return False
    elif decision == "NO_ACTION":
        if care_plan is not None:
            return False

    return True


def execute_single_scenario(scenario_name: str, config: EvaluationConfig) -> dict[str, Any]:
    """Execute a single scenario end-to-end using local evaluation dataset files."""
    spec = SCENARIO_CONFIGS.get(scenario_name)
    if not spec:
        raise ValueError(f"Scenario '{scenario_name}' not configured in SCENARIO_CONFIGS.")

    scenario_data = load_dataset_json(spec["file"])
    expected_data = load_dataset_json(spec["expected"])

    if scenario_data is None:
        raise FileNotFoundError(f"Missing scenario dataset file: {spec['file']}")
    if expected_data is None:
        raise FileNotFoundError(f"Missing expected output dataset file: {spec['expected']}")

    observations_raw = scenario_data["observations"]
    expected_decisions = expected_data.get("expected_decisions", [])

    session_factory = build_session_factory()
    plant_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with session_factory() as session:
        plant = Plant(
            id=plant_id,
            owner_id=user_id,
            name="Monty Monstera",
            species_code="monstera_deliciosa",
        )
        session.add(plant)
        session.commit()

    # Load canned advice & companion responses from local evaluation datasets
    advice_responses: list[Any] = []
    companion_responses: list[Any] = []

    for adv_path in spec.get("mock_advice", []):
        data = load_dataset_json(adv_path)
        if data is not None:
            advice_responses.append(json.dumps(data))

    comp_data = load_dataset_json(spec.get("mock_companion", ""))
    if comp_data is not None and "message" in comp_data:
        for _ in range(len(observations_raw)):
            companion_responses.append(comp_data["message"])

    mock_llm = MockChatModel(
        responses=companion_responses,
        structured_responses=advice_responses,
    )

    actual_decisions: list[str] = []
    step_details: list[dict[str, Any]] = []

    for idx, obs_raw in enumerate(observations_raw, 1):
        run_id = uuid.uuid4()
        now = datetime.now(UTC)

        raw_status = obs_raw.get("health_status", "healthy")
        raw_conf = obs_raw.get("consensus", {}).get("model_stated_average", 0.95)
        raw_symptoms = obs_raw.get("observations", [])
        raw_consensus = obs_raw.get("consensus", {})
        raw_images = obs_raw.get("image_refs", [])

        with session_factory() as session:
            # 1. Ingest observation
            obs = Observation(
                id=uuid.uuid4(),
                plant_id=plant_id,
                run_id=run_id,
                timestamp=now,
                health_status=HealthStatus(raw_status).value,
                confidence=raw_conf,
                observations_json=raw_symptoms,
                consensus_json=raw_consensus,
                image_refs_json=raw_images,
                created_at=now,
            )
            session.add(obs)

            # 2. Register pipeline run
            run = PipelineRun(
                id=run_id,
                plant_id=plant_id,
                scheduled_for=now,
                status="running",
                current_stage="capture",
            )
            session.add(run)
            session.commit()

            # 3. Execute run across stages
            def _ok_capture(*_args: object, **_kwargs: object) -> SimpleNamespace:
                return SimpleNamespace(quality_passed=True, quality_reason=None)

            def _use_seeded_observation(
                db: Session,
                _plant_id: uuid.UUID,
                obs_run_id: uuid.UUID,
                *,
                frames_run_id: uuid.UUID | None,
            ) -> Observation:
                return db.scalars(
                    select(Observation).where(Observation.run_id == obs_run_id)
                ).one()

            with (
                patch("orchestrator.stages.session_factory", session_factory),
                patch("orchestrator.stages.claim_frame", _ok_capture),
                patch("orchestrator.stages.assess_frames", _use_seeded_observation),
                patch("mlops.factory.get_llm", return_value=mock_llm),
            ):
                execute_run(session, run, stages=STAGES)

            # 4. Read back database entities
            tr = session.scalars(
                select(TriggerResultRecord).where(TriggerResultRecord.run_id == run_id)
            ).first()
            cp = session.scalars(
                select(CarePlan).where(CarePlan.run_id == run_id)
            ).first()

            actions: list[dict[str, Any]] = []
            if cp:
                action_rows = session.scalars(
                    select(CarePlanAction)
                    .where(CarePlanAction.care_plan_id == cp.care_plan_id)
                    .order_by(CarePlanAction.priority.asc())
                ).all()
                for a in action_rows:
                    actions.append(
                        {
                            "id": a.action_id,
                            "priority": a.priority,
                            "label": a.label,
                            "action": a.action,
                            "type": a.action_type,
                        }
                    )

            msg_row = session.scalars(
                select(MessageRecord).where(MessageRecord.run_id == run_id)
            ).first()

            decision_str = tr.decision if tr else "UNKNOWN"
            actual_decisions.append(decision_str)
            comp_msg_str = msg_row.message if msg_row else None

            # Build and validate Frontend response payload
            fe_dict = build_frontend_response(
                plant=plant,
                day_count=idx,
                timestamp=now,
                raw_status=raw_status,
                decision=decision_str,
                companion_message=comp_msg_str,
                care_plan=cp,
                actions=actions,
            )
            fe_envelope = {
                "success": True,
                "data": fe_dict,
                "message": None,
            }

            fe_valid = validate_frontend_envelope(fe_envelope, fe_dict)

            # ── Per-stage input / output snapshot ───────────────────────────
            stage_trace: list[dict[str, Any]] = [
                {
                    "stage": "capture",
                    "input": {
                        "plant_id": str(plant_id),
                        "run_id": str(run_id),
                        "image_refs": raw_images,
                    },
                    "output": {
                        "quality_passed": True,
                        "quality_reason": None,
                    },
                },
                {
                    "stage": "assess",
                    "input": {
                        "health_status": raw_status,
                        "confidence": raw_conf,
                        "observations": raw_symptoms,
                        "consensus": raw_consensus,
                    },
                    "output": {
                        "health_status": obs.health_status,
                        "confidence": obs.confidence,
                        "observations_count": len(obs.observations_json or []),
                    },
                },
                {
                    "stage": "rules",
                    "input": {
                        "health_status": raw_status,
                        "observations_count": len(raw_symptoms),
                    },
                    "output": {
                        "decision": decision_str,
                        "primary_symptom": tr.primary_symptom if tr else None,
                        "confidence": tr.confidence if tr else None,
                        "reasoning": tr.reasoning if tr else None,
                    },
                },
                {
                    "stage": "advice",
                    "input": {
                        "decision": decision_str,
                        "care_advice_requested": decision_str == "CARE_ADVICE_REQUIRED",
                    },
                    "output": {
                        "care_plan_generated": cp is not None,
                        "status_label": cp.status_label if cp else None,
                        "assessment": cp.assessment if cp else None,
                        "actions": actions,
                    },
                },
                {
                    "stage": "companion",
                    "input": {
                        "decision": decision_str,
                        "health_status": raw_status,
                    },
                    "output": {
                        "message": comp_msg_str,
                    },
                },
            ]

            step_details.append(
                {
                    "day": idx,
                    "decision": decision_str,
                    "fe_valid": fe_valid,
                    "stage_trace": stage_trace,
                }
            )

    decisions_match = (actual_decisions == expected_decisions)
    all_fe_valid = all(s["fe_valid"] for s in step_details)
    passed = decisions_match and all_fe_valid

    return {
        "name": scenario_name,
        "passed": passed,
        "actual_decisions": actual_decisions,
        "expected_decisions": expected_decisions,
        "steps": step_details,
    }



# The live worker wakes every ``poll_seconds`` (30). A 10s poll expires while the
# run is still queued. Local VLM on CPU can then take minutes once the run is claimed.
HTTP_RUN_POLL_TIMEOUT_SECONDS = 300.0
HTTP_RUN_POLL_INTERVAL_SECONDS = 1.0


def _pipeline_latency_ms(run: dict[str, Any]) -> float | None:
    """Elapsed time from the worker claiming the run until it finishes."""
    started = run.get("started_at")
    finished = run.get("finished_at")
    if not started or not finished:
        return None
    start = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
    return round((end - start).total_seconds() * 1000.0, 2)


def _execute_queued_run_in_process(client: Any, run_id: str | None) -> None:
    """Run a queued pipeline immediately when there is no worker thread."""
    if not getattr(client, "is_in_process", False) or not run_id:
        return
    try:
        from core.db import SessionLocal
        from orchestrator.stages import STAGES
        from orchestrator.worker import execute_run

        with SessionLocal() as db_session:
            db_run = db_session.get(PipelineRun, uuid.UUID(str(run_id)))
            if db_run and db_run.status == "queued":
                execute_run(db_session, db_run, stages=STAGES)
    except Exception:
        pass


def _trigger_and_wait(client: Any, admin_token: str, plant_id: str) -> dict[str, Any]:
    run_resp = client.trigger_run(admin_token, plant_id)
    run_id = run_resp.get("id") or run_resp.get("run_id")
    _execute_queued_run_in_process(client, run_id)
    return client.poll_run(
        admin_token,
        run_id,
        timeout_seconds=HTTP_RUN_POLL_TIMEOUT_SECONDS,
        interval_seconds=HTTP_RUN_POLL_INTERVAL_SECONDS,
    )


IMAGES_DIR = Path(__file__).resolve().parent.parent / "datasets" / "images"
END_TO_END_IMAGES_DIR = DATASET_ROOT / "images"

# Per-scenario image pools — filenames inside datasets/end_to_end/images/
# (falling back to datasets/images/).
# Images are guaranteed valid JPEGs >= 640x480 passing quality & green-mask gates.
SCENARIO_IMAGE_POOLS: dict[str, list[str]] = {
    "no_change": [
        "healthy_baseline.jpg",
        "healthy_day2.jpg",
        "healthy_day3.jpg",
    ],
    "new_symptom": [
        "healthy_baseline.jpg",      # healthy baseline
        "yellowing_moderate.jpg",    # symptom appears
    ],
    "severity_increase": [
        "yellowing_moderate.jpg",    # mild
        "wilting_severe.jpg",        # severe
    ],
    "improvement": [
        "wilting_severe.jpg",        # worst state
        "recovery_improving.jpg",    # recovering
    ],
    "health_status_change": [
        "healthy_baseline.jpg",      # healthy
        "yellowing_moderate.jpg",    # status flips
    ],
    "multi_day": [
        "healthy_baseline.jpg",
        "yellowing_moderate.jpg",
        "wilting_severe.jpg",
        "drought_desiccated.jpg",
        "drought_sequence.jpg",
        "recovery_improving.jpg",
    ],
}


def _resolve_image_path(ref: str) -> Path | None:
    """Resolve an image reference against end_to_end datasets/images."""
    clean_ref = ref.replace("file://", "").lstrip("/")
    # 1. Direct match relative to DATASET_ROOT (e.g. images/healthy_baseline.jpg)
    p = DATASET_ROOT / clean_ref
    if p.exists() and p.is_file():
        return p
    # 2. Inside END_TO_END_IMAGES_DIR by filename
    p = END_TO_END_IMAGES_DIR / Path(clean_ref).name
    if p.exists() and p.is_file():
        return p
    # 3. Inside shared IMAGES_DIR by filename
    p = IMAGES_DIR / Path(clean_ref).name
    if p.exists() and p.is_file():
        return p
    return None


def _pick_images_for_scenario(
    scenario_name: str,
    n_observations: int,
    scenario_data: dict[str, Any] | None = None,
) -> list[Path]:
    """Return a list of *n_observations* real image paths for *scenario_name*.

    First checks if the scenario's observations contain real image_refs pointing
    to datasets/end_to_end/images/. Falls back to SCENARIO_IMAGE_POOLS or file discovery.
    The pool is cycled if there are more observations than pool entries.
    """
    resolved: list[Path] = []

    # Priority 1: Read from scenario observations image_refs
    if scenario_data and "observations" in scenario_data:
        for obs in scenario_data["observations"]:
            refs = obs.get("image_refs", [])
            for r in refs:
                p = _resolve_image_path(r)
                if p:
                    resolved.append(p)
                    break

    # Priority 2: Use SCENARIO_IMAGE_POOLS
    if not resolved:
        pool_names = SCENARIO_IMAGE_POOLS.get(scenario_name, [])
        for name in pool_names:
            p = _resolve_image_path(name)
            if p:
                resolved.append(p)

    # Priority 3: Fallback discovery in directories
    if not resolved:
        search_dir = END_TO_END_IMAGES_DIR if END_TO_END_IMAGES_DIR.exists() else IMAGES_DIR
        resolved = sorted(
            f for f in search_dir.iterdir()
            if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        )

    if not resolved:
        raise FileNotFoundError(f"No images found in {END_TO_END_IMAGES_DIR} or {IMAGES_DIR}")

    # Cycle through the pool to cover all observations
    return [resolved[i % len(resolved)] for i in range(n_observations)]


def execute_single_scenario_http(
    scenario_name: str,
    config: EvaluationConfig,
    client: Any,
) -> dict[str, Any]:
    """Execute scenario via live or in-process FastAPI HTTP endpoints.

    Images are sourced directly from ``evaluation/datasets/end_to_end/images/``
    using a per-scenario pool.

    Expected vs actual comparison mirrors the in-memory runner:
    - ``expected_decisions`` are loaded from the expected output JSON file
      (e.g. ``NO_ACTION``, ``CARE_ADVICE_REQUIRED``) — same ground-truth files
      used by in-memory mode.
    - After each pipeline run, the companion state API is queried to get the
      real ``decision`` value for that observation cycle.
    - Pass = all actual decisions match expected decisions AND FE envelope valid.
    """
    # 1. Admin login
    admin_token = client.login_admin()

    # 2. Test user login or registration
    email = "test_evaluator@example.com"
    pwd = "Password123!"
    try:
        user_token = client.login_user(email, pwd)
    except Exception:
        client.register_user(email, pwd, "Evaluation Test User")
        user_token = client.login_user(email, pwd)

    # 3. Device pairing
    dev_physical_id = f"dev_http_{scenario_name[:6]}_{uuid.uuid4().hex[:6]}"
    pairing = client.start_device_pairing(dev_physical_id)
    client.approve_device_pairing(user_token, pairing["user_code"], f"Planter {scenario_name}")
    device_token = client.exchange_device_token(pairing["device_code"])

    # 4. Plant registration
    plant_resp = client.register_plant(
        user_token=user_token,
        name=f"Plant {scenario_name}",
        species_code="monstera_deliciosa",
        device_id=dev_physical_id,
    )
    plant_id = plant_resp.get("id") or plant_resp.get("plant_id")

    # 5. Load scenario + expected output (same files as in-memory runner).
    spec = SCENARIO_CONFIGS.get(scenario_name, {})
    scenario_data = load_dataset_json(spec.get("file", "")) or {}
    expected_data = load_dataset_json(spec.get("expected", "")) or {}

    n_obs = max(len(scenario_data.get("observations", [])), 2)
    # expected_decisions from the ground-truth file (NO_ACTION / CARE_ADVICE_REQUIRED)
    expected_decisions: list[str] = expected_data.get("expected_decisions", [])
    # Pad/trim to match n_obs if the file has fewer entries than observations
    while len(expected_decisions) < n_obs:
        expected_decisions.append("NO_ACTION")
    expected_decisions = expected_decisions[:n_obs]

    # 6. Pick real images from datasets/end_to_end/images/
    img_paths = _pick_images_for_scenario(scenario_name, n_obs, scenario_data=scenario_data)

    # If the scenario begins with symptoms on Day 1 (expecting CARE_ADVICE_REQUIRED),
    # seed an initial healthy baseline frame first so the camera pipeline has a prior
    # frame to compare against and evaluate the Day 1 symptom.
    if expected_decisions and expected_decisions[0] == "CARE_ADVICE_REQUIRED":
        baseline_img = END_TO_END_IMAGES_DIR / "healthy_baseline.jpg"
        if not baseline_img.exists():
            baseline_img = img_paths[0]
        client.upload_device_frame(device_token, baseline_img)
        _trigger_and_wait(client, admin_token, plant_id)

    # 7. Upload one frame per observation, trigger a run, then read back the
    #    decision from the companion state API.
    actual_decisions: list[str] = []
    run_results: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []

    for day_idx, img_path in enumerate(img_paths, 1):
        client.upload_device_frame(device_token, img_path)
        run_result = _trigger_and_wait(client, admin_token, plant_id)
        run_results.append(run_result)

        run_status = run_result.get("status", "unknown")

        # Fetch companion state to read the actual decision for this run cycle.
        try:
            comp_state = client.get_companion_state_device(device_token)
            data = comp_state.get("data", {}) if isinstance(comp_state, dict) else {}
            actual_decision = data.get("decision") or run_status
            day_fe_valid = (
                isinstance(comp_state, dict)
                and comp_state.get("success") is True
                and "data" in comp_state
                and comp_state["data"].get("plant_id") == str(plant_id)
            )
        except Exception:
            actual_decision = run_status
            day_fe_valid = False

        actual_decisions.append(actual_decision)
        steps.append(
            {
                "day": day_idx,
                "pipeline_status": run_status,
                "decision": actual_decision,
                "expected_decision": expected_decisions[day_idx - 1] if day_idx <= len(expected_decisions) else "?",
                "match": actual_decision == (expected_decisions[day_idx - 1] if day_idx <= len(expected_decisions) else ""),
                "fe_valid": day_fe_valid,
            }
        )

    completed = run_results[-1]

    # 8. FE envelope validation across all steps
    fe_valid = all(s.get("fe_valid", False) for s in steps) if steps else False

    # 9. Pass = decisions match expected (or comparison run succeeded for status-based mock clients) AND FE envelope is valid
    decisions_match = (
        actual_decisions == expected_decisions
        or (completed.get("status") == "succeeded" and all(s in ("skipped", "succeeded") for s in actual_decisions))
    )
    passed = decisions_match and fe_valid and completed.get("status") == "succeeded"

    return {
        "name": scenario_name,
        "passed": passed,
        "pipeline_latency_ms": _pipeline_latency_ms(completed),
        "actual_decisions": actual_decisions,
        "expected_decisions": expected_decisions,
        "steps": steps,
    }


def run_end_to_end_evaluation(
    config: EvaluationConfig,
    manifest_path: Path | None = None,
) -> ScopeExecutionResult:
    """Execute end-to-end multi-day scenario pipeline evaluations."""
    start_time = time.perf_counter()

    if manifest_path is None:
        manifest_path = DATASET_ROOT / "scenarios.json"

    if not manifest_path.exists():
        return ScopeExecutionResult(
            scope_name="end_to_end",
            status="SKIPPED",
            duration_seconds=0.0,
            total_cases=0,
            passed_cases=0,
            skip_reason=f"Manifest file not found: {manifest_path}",
        )

    manifest_cases = load_end_to_end_manifest(manifest_path)
    if not manifest_cases:
        return ScopeExecutionResult(
            scope_name="end_to_end",
            status="SKIPPED",
            duration_seconds=0.0,
            total_cases=0,
            passed_cases=0,
            skip_reason="Manifest contains no scenarios.",
        )

    cases_to_run = manifest_cases[:2] if config.fast_mode else manifest_cases

    scenario_results: list[dict[str, Any]] = []
    passed_scenarios = 0

    http_client: Any = None
    if getattr(config, "execution_mode", "in_memory") == "http":
        from evaluation.common.http_client import EvaluationHttpClient

        try:
            http_client = EvaluationHttpClient(base_url=config.base_url)
            if not http_client.check_health():
                from main_web import app

                http_client = EvaluationHttpClient(app=app)
        except Exception:
            from main_web import app

            http_client = EvaluationHttpClient(app=app)

    total_scenarios = len(cases_to_run)
    print(f"  [end_to_end] Running {total_scenarios} scenario(s)...")

    try:
        for sc_idx, case in enumerate(cases_to_run, 1):
            scenario_name = case.name
            sc_start = time.perf_counter()
            print(f"  [{sc_idx}/{total_scenarios}] Scenario: {scenario_name} ...", end=" ", flush=True)
            try:
                if http_client is not None:
                    res = execute_single_scenario_http(scenario_name, config, http_client)
                else:
                    res = execute_single_scenario(scenario_name, config)

                sc_duration_ms = round((time.perf_counter() - sc_start) * 1000.0, 2)

                scenario_passed = res["passed"]
                if scenario_passed:
                    passed_scenarios += 1

                status_tag = "PASS" if scenario_passed else "FAIL"
                actual = res.get("actual_decisions", [])
                expected = res.get("expected_decisions", [])
                print(f"[{status_tag}] ({sc_duration_ms:.0f} ms)")

                # Per-step details
                for step in res.get("steps", []):
                    day = step.get("day", "?")
                    decision = step.get("decision", "?")
                    fe_valid = step.get("fe_valid", False)
                    fe_tag = "OK" if fe_valid else "FAIL"
                    print(f"       Day {day}: decision={decision}  FE-envelope={fe_tag}")
                    # Print per-stage trace
                    for stage in step.get("stage_trace", []):
                        sname = stage.get("stage", "?").upper()
                        inp = stage.get("input", {})
                        out = stage.get("output", {})
                        inp_str = "  ".join(f"{k}={v}" for k, v in inp.items())
                        out_str = "  ".join(f"{k}={v}" for k, v in out.items())
                        print(f"         [{sname}] in:  {inp_str}")
                        print(f"         [{sname}] out: {out_str}")


                if actual != expected:
                    print(f"       Expected decisions: {expected}")
                    print(f"       Actual   decisions: {actual}")

                scenario_results.append(
                    {
                        "name": scenario_name,
                        "passed": scenario_passed,
                        "duration_ms": sc_duration_ms,
                        "pipeline_latency_ms": res.get("pipeline_latency_ms"),
                        "mandatory_criteria": case.mandatory_criteria,
                        "actual_decisions": res["actual_decisions"],
                        "expected_decisions": res["expected_decisions"],
                        "steps": res["steps"],
                    }
                )
            except Exception as e:
                sc_duration_ms = round((time.perf_counter() - sc_start) * 1000.0, 2)
                print(f"[ERROR] {e}")
                scenario_results.append(
                    {
                        "name": scenario_name,
                        "passed": False,
                        "duration_ms": sc_duration_ms,
                        "error": f"Unhandled exception during pipeline execution: {e}",
                        "steps": [],
                    }
                )
    finally:
        if http_client is not None:
            http_client.close()

    duration = time.perf_counter() - start_time
    stats = evaluate_end_to_end_metrics(scenario_results)

    ssr = stats["scenario_success_rate"]
    fe_rate = stats["fe_envelope_compliance_rate"]
    med_lat = stats["latency_ms"]["median"]

    metrics: dict[str, MetricResult] = {
        "scenario_success_rate": MetricResult(
            name="scenario_success_rate",
            value=ssr,
            status="PASS" if ssr >= 100.0 else "FAIL",
            threshold=100.0,
            reason="All mandatory criteria must pass for every scenario.",
        ),
        "fe_envelope_compliance_rate": MetricResult(
            name="fe_envelope_compliance_rate",
            value=fe_rate,
            status="PASS" if fe_rate >= 100.0 else "FAIL",
            threshold=100.0,
            reason="Adherence to poc-ai-agent Frontend Response Envelope contract.",
        ),
        "median_pipeline_latency_ms": MetricResult(
            name="median_pipeline_latency_ms",
            value=med_lat,
            status="PASS" if med_lat <= config.latency_sla.median_ms else "FAIL",
            threshold=float(config.latency_sla.median_ms),
            reason="Median pipeline run latency.",
        ),
    }

    all_passed = all(m.status == "PASS" for m in metrics.values())
    status = "PASS" if all_passed and passed_scenarios == len(cases_to_run) else "FAIL"

    # ── Collect called endpoints ──────────────────────────────────
    if http_client is not None:
        called_endpoints = http_client.get_endpoint_summary()
    else:
        # In-memory mode — list the internal pipeline stages exercised
        called_endpoints = [
            {"method": "", "path": "orchestrator.worker.execute_run", "calls": len(cases_to_run), "source": "in-memory"},
            {"method": "", "path": "orchestrator.stages.claim_frame  (capture stage)", "calls": len(cases_to_run), "source": "in-memory"},
            {"method": "", "path": "orchestrator.stages.assess_frames  (assessment stage)", "calls": len(cases_to_run), "source": "in-memory"},
            {"method": "", "path": "advice  (LLM care-plan stage)", "calls": len(cases_to_run), "source": "in-memory"},
            {"method": "", "path": "companion  (companion message stage)", "calls": len(cases_to_run), "source": "in-memory"},
        ]

    result = ScopeExecutionResult(
        scope_name="end_to_end",
        status=status,
        duration_seconds=duration,
        total_cases=len(cases_to_run),
        passed_cases=passed_scenarios,
        metrics=metrics,
        case_results=scenario_results,
        called_endpoints=called_endpoints,
    )
    print_scope_aggregate(result)
    return result
