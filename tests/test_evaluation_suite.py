"""Automated unit and smoke tests for the Pet-Plant evaluation suite."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.common.config import EvaluationConfig, runtime_models
from evaluation.common.loaders import (
    ManifestValidationError,
    load_end_to_end_manifest,
)
from evaluation.common.metrics import (
    ConfusionMatrix,
    calculate_iou,
    calculate_jaccard,
    calculate_macro_f1,
    calculate_percentile,
    calculate_text_similarity,
)
from evaluation.common.reporting import (
    EvaluationRunSummary,
    generate_markdown_summary,
    write_run_report,
)
from evaluation.end_to_end.run import run_end_to_end_evaluation, validate_frontend_envelope
from evaluation.llm.run import run_llm_evaluation
from evaluation.scripts.cleanup import (
    ALLOWED_REPORTS_DIR,
    CleanupSecurityError,
    clean_evaluation_reports,
    verify_safe_path,
)
from evaluation.scripts.cli import cmd_run, cmd_validate
from evaluation.vlm.run import run_vlm_evaluation


# --- 1. Common Config & Loaders Tests ---

def test_common_config_defaults() -> None:
    cfg = EvaluationConfig.load()
    assert cfg.confidence_threshold == 0.5
    assert cfg.quality_thresholds.min_width == 640
    assert cfg.quality_thresholds.min_height == 480
    assert cfg.quality_thresholds.min_blur_score == 50.0


def test_manifest_validation_success(tmp_path: Path) -> None:
    manifest_data = {
        "version": "1.0.0",
        "scope": "end_to_end",
        "scenarios": [
            {
                "name": "test_scenario",
                "scenario_file": "scenarios/test.json",
                "expected_file": "expected/test.json",
                "mandatory_criteria": ["C1"],
            }
        ],
    }
    p = tmp_path / "valid_manifest.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)

    cases = load_end_to_end_manifest(p)
    assert len(cases) == 1
    assert cases[0].name == "test_scenario"
    assert cases[0].mandatory_criteria == ["C1"]


def test_manifest_validation_failure_on_invalid_scope(tmp_path: Path) -> None:
    invalid_data = {
        "version": "1.0.0",
        "scope": "wrong_scope",
        "scenarios": [],
    }
    p = tmp_path / "invalid_manifest.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(invalid_data, f)

    with pytest.raises(ManifestValidationError):
        load_end_to_end_manifest(p)


# --- 2. Metrics Mathematics Tests ---

def test_confusion_matrix_metrics() -> None:
    # TP=8, TN=90, FP=2, FN=0
    cm = ConfusionMatrix(tp=8, tn=90, fp=2, fn=0)
    assert cm.total == 100
    assert cm.accuracy == 0.98
    assert cm.precision == 0.8
    assert cm.recall == 1.0
    assert cm.f1_score == round(2 * 0.8 * 1.0 / 1.8, 4)


def test_confusion_matrix_zero_division() -> None:
    cm = ConfusionMatrix(tp=0, tn=0, fp=0, fn=0)
    assert cm.accuracy == 1.0
    assert cm.precision == 1.0
    assert cm.recall == 1.0
    assert cm.f1_score == 1.0


def test_macro_f1() -> None:
    scores = {"class_a": 0.8, "class_b": 0.6, "class_c": 1.0}
    assert calculate_macro_f1(scores) == 0.8


def test_iou_calculation() -> None:
    box_a = [0, 0, 10, 10]
    box_b = [0, 0, 10, 10]
    assert calculate_iou(box_a, box_b) == 1.0

    box_c = [10, 10, 10, 10]
    assert calculate_iou(box_a, box_c) == 0.0


def test_runtime_models_follow_settings_when_openai_is_unavailable() -> None:
    settings = SimpleNamespace(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_api_key="",
        llm_api_base="https://api.openai.com/v1",
        ollama_host="http://localhost:11434",
        ollama_model="mistral:7b",
        embedding_provider="",
        embedding_model="nomic-embed-text:latest",
        vlm_provider="local",
        vlm_local_model_path="models/internvl3_5-2b",
        vlm_api_base="",
    )

    models = runtime_models(settings)

    assert models.llm_provider == "ollama"
    assert models.llm_model == "mistral:7b"
    assert models.embedding_provider == "ollama"
    assert models.embedding_model == "nomic-embed-text:latest"
    assert models.vlm_provider == "local"
    assert models.vlm_model == "models/internvl3_5-2b"


def test_runtime_models_keep_openai_when_the_key_is_set() -> None:
    settings = SimpleNamespace(
        llm_provider="openai",
        llm_model="gpt-4o-mini",
        llm_api_key="sk-test",
        llm_api_base="https://api.openai.com/v1",
        ollama_host="http://localhost:11434",
        ollama_model="mistral:7b",
        embedding_provider="",
        embedding_model="text-embedding-3-small",
        vlm_provider="vllm",
        vlm_local_model_path="models/internvl3_5-2b",
        vlm_api_base="http://localhost:8001/v1",
    )

    models = runtime_models(settings)

    assert models.llm_model == "gpt-4o-mini"
    assert models.embedding_provider == "openai"
    assert models.embedding_model == "text-embedding-3-small"
    assert models.vlm_model == "http://localhost:8001/v1"


def test_jaccard_similarity() -> None:
    assert calculate_jaccard({"a", "b"}, {"a", "b"}) == 1.0
    assert calculate_jaccard({"a"}, {"b"}) == 0.0
    assert calculate_jaccard(set(), set()) == 1.0


def test_percentile_calculation() -> None:
    vals = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert calculate_percentile(vals, 50.0) == 30.0
    assert calculate_percentile([], 50.0) == 0.0


def test_text_similarity_and_difference_metrics() -> None:
    # 1. Exact match
    res_exact = calculate_text_similarity("Hello world", "Hello world")
    assert res_exact["semantic_similarity"] == 100.0
    assert res_exact["response_difference"] == 0.0

    # 2. Empty text
    res_empty = calculate_text_similarity("Some text", "")
    assert res_empty["semantic_similarity"] == 0.0
    assert res_empty["response_difference"] == 100.0

    # 3. Similar paraphrased texts
    t1 = "Lower leaves show mild discoloration likely related to minor moisture fluctuation."
    t2 = "Lower leaves exhibit slight yellowing, probably caused by uneven watering and moisture issues."
    res_sim = calculate_text_similarity(t1, t2)
    assert res_sim["semantic_similarity"] > 70.0
    assert res_sim["response_difference"] < 30.0
    assert round(res_sim["composite_similarity"] + res_sim["response_difference"], 1) == 100.0


# --- 3. Scope Runners Tests ---

def test_vlm_runner() -> None:
    cfg = EvaluationConfig.load()
    cfg.fast_mode = True
    res = run_vlm_evaluation(cfg, limit=10)
    assert res.scope_name == "vlm"
    assert res.status == "PASS"
    assert res.total_cases == 10
    assert res.passed_cases == 10
    assert "health_status_accuracy" in res.metrics
    assert "health_status_f1" in res.metrics
    assert "symptoms_micro_f1" in res.metrics
    assert "symptoms_macro_f1" in res.metrics
    assert res.metrics["health_status_accuracy"].value >= 75.0
    assert res.metrics["health_status_f1"].value >= 75.0
    assert "mean_semantic_similarity" not in res.metrics
    assert "mean_response_difference" not in res.metrics



def test_llm_runner_similarity_and_percentage_metrics() -> None:
    cfg = EvaluationConfig.load()
    res = run_llm_evaluation(cfg)
    assert res.scope_name == "llm"
    assert res.status == "PASS"
    assert res.total_cases == 5
    assert res.passed_cases == 5
    assert "mean_semantic_similarity" in res.metrics
    assert "mean_response_difference" in res.metrics
    assert "mean_action_alignment" in res.metrics
    assert res.metrics["advice_schema_conformance"].value == 100.0
    assert res.metrics["mean_semantic_similarity"].value >= 70.0
    assert res.metrics["mean_response_difference"].value <= 30.0
    assert res.metrics["mean_action_alignment"].value >= 80.0


def test_markdown_report_formatting_percentages() -> None:
    cfg = EvaluationConfig.load()
    llm_res = run_llm_evaluation(cfg)
    summary = EvaluationRunSummary(
        run_id="run_test_formatting_001",
        timestamp_utc="2026-10-17T07:00:00Z",
        duration_seconds=1.23,
        overall_status="PASS",
        scopes={"llm": llm_res},
        git_commit="abc1234",
    )
    md = generate_markdown_summary(summary)
    # Check that % symbol is displayed in metrics and tables
    assert "%" in md
    assert "Response Similarity & Difference Breakdown" in md
    assert "CASE-ADVICE-001" in md
    assert "advice_schema_conformance=100.00%" in md
    assert "(100 - (similarity) * 100)" in md



def test_end_to_end_fast_runner() -> None:
    cfg = EvaluationConfig.load()
    cfg.fast_mode = True
    res = run_end_to_end_evaluation(cfg)
    assert res.scope_name == "end_to_end"
    assert res.status == "PASS"
    assert res.total_cases == 2
    assert res.passed_cases == 2
    assert res.metrics["scenario_success_rate"].value == 100.0



def test_frontend_envelope_validator() -> None:
    valid_env = {
        "success": True,
        "data": {
            "plant_id": "p1",
            "name": "Monstera",
            "species": "deliciosa",
            "dayCount": 1,
            "timestamp": "2026-09-01T10:00:00Z",
            "health_status": "healthy",
            "decision": "NO_ACTION",
            "companion_message": "Feeling fine",
            "care_plan": None,
        },
    }
    assert validate_frontend_envelope(valid_env, valid_env["data"]) is True

    # Invalid: care_plan present on NO_ACTION
    invalid_env = dict(valid_env)
    invalid_env["data"] = dict(valid_env["data"])
    invalid_env["data"]["care_plan"] = {"actions": []}
    assert validate_frontend_envelope(invalid_env, invalid_env["data"]) is False


# --- 4. Cleanup Safety Tests ---

def test_verify_safe_path_protection(tmp_path: Path) -> None:
    # A path outside ALLOWED_REPORTS_DIR must be rejected
    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    with pytest.raises(CleanupSecurityError):
        verify_safe_path(outside_dir)


def test_cleanup_dry_run_and_preservation(tmp_path: Path) -> None:
    # Setup mock reports dir inside ALLOWED_REPORTS_DIR
    mock_run = ALLOWED_REPORTS_DIR / "_test_mock_run_temp"
    mock_run.mkdir(parents=True, exist_ok=True)
    mock_file = mock_run / "test.json"
    mock_file.write_text("{}", encoding="utf-8")

    # 1. Dry run should report file without deleting
    deleted, _ = clean_evaluation_reports(ALLOWED_REPORTS_DIR, dry_run=True, keep_latest=True)
    assert any(p.name == "_test_mock_run_temp" for p in deleted)
    assert mock_file.exists()

    # 2. Real cleanup with keep_latest
    deleted_real, _ = clean_evaluation_reports(ALLOWED_REPORTS_DIR, dry_run=False, keep_latest=True)
    assert not mock_run.exists()


# --- 5. VLM Structured Classification & Batch Photo Tests ---

def test_vlm_classification_metrics() -> None:
    from evaluation.vlm.metrics import (
        calculate_classification_metrics,
        evaluate_probe_findings,
        evaluate_symptoms_classification,
    )

    # 1. Confusion matrix math
    res = calculate_classification_metrics(tp=4, fp=1, fn=1, tn=4)
    assert res["precision"] == 80.0
    assert res["recall"] == 80.0
    assert res["f1"] == 80.0
    assert res["accuracy"] == 80.0

    # 2. Symptoms classification
    exp_sym = ["leaf_yellowing", "drooping_petioles"]
    act_sym = ["leaf_yellowing", "browning_edges"]
    sym_res = evaluate_symptoms_classification(exp_sym, act_sym)
    assert sym_res["tp"] == 1.0
    assert sym_res["fp"] == 1.0
    assert sym_res["fn"] == 1.0

    # 3. Probe findings
    exp_probes = [{"slug": "overwatering", "answer": "yes"}, {"slug": "pests", "answer": "no"}]
    act_probes = [{"slug": "overwatering", "answer": "yes"}, {"slug": "pests", "answer": "no"}]
    probe_res = evaluate_probe_findings(exp_probes, act_probes)
    assert probe_res["f1"] == 100.0
    assert probe_res["accuracy"] == 100.0


def test_batch_photo_evaluation_and_averaging() -> None:
    from evaluation.vlm.run import IMAGES_DIR, evaluate_batch_photos

    cfg = EvaluationConfig.load()
    summary = evaluate_batch_photos(IMAGES_DIR, cfg)

    assert summary["total_photos"] >= 2
    assert summary["successful_photos"] > 0
    assert summary["success_rate_pct"] > 0.0
    assert "avg_f1_score" in summary
    assert "avg_precision" in summary
    assert "avg_recall" in summary
    assert "avg_accuracy" in summary
    assert "avg_semantic_similarity_pct" not in summary
    assert "avg_response_difference_pct" not in summary
    assert len(summary["photo_details"]) == summary["total_photos"]



def test_http_client_in_process() -> None:
    from evaluation.common.http_client import EvaluationHttpClient
    from main_web import app

    with EvaluationHttpClient(app=app) as client:
        assert client.check_health() is True
        # Verify 401 on unauthenticated companion endpoint
        resp = client.client.get("/companion/devices/me/state")
        assert resp.status_code == 401


class _ScriptedHttpClient:
    """Records HTTP scenario calls and returns a baseline skip, then a comparison run."""

    is_in_process = False

    def __init__(self, comparison_status: str = "succeeded") -> None:
        self.comparison_status = comparison_status
        self.uploads = 0
        self.poll_timeouts: list[float] = []
        self._runs = 0

    def login_admin(self) -> str:
        return "admin-token"

    def login_user(self, email: str, password: str) -> str:
        return "user-token"

    def start_device_pairing(self, physical_id: str) -> dict[str, str]:
        return {"user_code": "user-code", "device_code": "device-code"}

    def approve_device_pairing(self, user_token: str, user_code: str, name: str) -> dict[str, str]:
        return {}

    def exchange_device_token(self, device_code: str) -> str:
        return "ppd-token"

    def register_plant(self, **kwargs: object) -> dict[str, str]:
        return {"id": "plant-1"}

    def upload_device_frame(self, device_token: str, image_path: object) -> dict[str, str]:
        self.uploads += 1
        return {}

    def trigger_run(self, admin_token: str, plant_id: str) -> dict[str, str]:
        self._runs += 1
        return {"id": f"run-{self._runs}"}

    def poll_run(
        self,
        admin_token: str,
        run_id: str,
        timeout_seconds: float = 30.0,
        interval_seconds: float = 0.5,
    ) -> dict[str, str]:
        self.poll_timeouts.append(timeout_seconds)
        if self._runs == 1:
            return {
                "status": "skipped",
                "started_at": "2026-10-17T12:39:05.587072+00:00",
                "finished_at": "2026-10-17T12:39:05.609571+00:00",
            }
        return {
            "status": self.comparison_status,
            "started_at": "2026-10-17T12:40:05.000000+00:00",
            "finished_at": "2026-10-17T12:40:06.000000+00:00",
        }

    def get_companion_state_device(self, device_token: str) -> dict[str, object]:
        return {"success": True, "data": {"plant_id": "plant-1"}}


def test_http_scenario_claims_a_baseline_before_expecting_success() -> None:
    """A new plant needs two claimed frames, and the live worker wakes every 30s."""
    from evaluation.end_to_end.run import execute_single_scenario_http

    client = _ScriptedHttpClient()
    result = execute_single_scenario_http("no_change", EvaluationConfig.load(), client)

    assert client.uploads == 2
    assert client.poll_timeouts
    assert all(timeout > 30.0 for timeout in client.poll_timeouts)
    assert result["passed"] is True
    assert result["actual_decisions"] == ["skipped", "succeeded"]
    assert result["pipeline_latency_ms"] == 1000.0


def test_http_scenario_does_not_pass_when_the_comparison_run_is_skipped() -> None:
    from evaluation.end_to_end.run import execute_single_scenario_http

    client = _ScriptedHttpClient(comparison_status="skipped")
    result = execute_single_scenario_http("no_change", EvaluationConfig.load(), client)

    assert result["passed"] is False
    assert result["actual_decisions"] == ["skipped", "skipped"]


def test_pipeline_latency_ignores_queue_wait() -> None:
    from evaluation.end_to_end.metrics import evaluate_end_to_end_metrics

    stats = evaluate_end_to_end_metrics(
        [
            {
                "passed": True,
                "duration_ms": 12000.0,
                "pipeline_latency_ms": 40.0,
                "steps": [{"fe_valid": True}],
            }
        ]
    )

    assert stats["latency_ms"]["median"] == 40.0


def test_fixture_lifecycle_setup_and_cleanup() -> None:
    from scripts.cleanup_evaluation_fixtures import cleanup_fixtures
    from scripts.init_evaluation_fixtures import setup_fixtures

    # 1. Setup fixtures
    seeded = setup_fixtures()
    assert "user_id" in seeded
    assert "device_id" in seeded
    assert "plant_id" in seeded

    # 2. Cleanup fixtures
    deleted = cleanup_fixtures()
    assert deleted["test_users"] >= 1
    assert deleted["devices"] >= 1
    assert deleted["plants"] >= 1
