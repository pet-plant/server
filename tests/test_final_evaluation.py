"""Unit and integration tests for final dataset VLM condition evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evaluation.common.config import EvaluationConfig
from evaluation.vlm.final_dataset import (
    FinalDatasetSample,
    SpeciesMetadata,
    load_final_dataset,
)
from evaluation.vlm.metrics import (
    evaluate_final_dataset_metrics,
    normalize_health_status,
)
from evaluation.vlm.predictor import (
    FinalDatasetPredictor,
    build_condition_prompt,
    extract_json_from_text,
)
from evaluation.vlm.run import run_final_dataset_evaluation


def test_load_final_dataset_structure():
    """Verify that final dataset loads all 505 human-reviewed images and species metadata."""
    dataset = load_final_dataset(verify_images=True)
    assert len(dataset) == 505
    assert len(dataset.species_meta) == 10
    assert len(dataset.symptom_descriptions) >= 18

    # Check status distribution
    status_counts = dataset.status_counts
    assert status_counts["healthy"] == 250
    assert status_counts["unhealthy"] == 255

    # Check species representation
    species_counts = dataset.species_counts
    assert len(species_counts) == 10
    assert "monstera" in species_counts
    assert "aloe_vera" in species_counts
    assert "snake_plant" in species_counts

    # Verify first sample has resolved image path and valid metadata
    sample_0 = dataset[0]
    assert sample_0.resolved_image_path is not None
    assert sample_0.resolved_image_path.exists()
    assert sample_0.species in dataset.species_meta
    meta = dataset.species_meta[sample_0.species]
    assert len(meta.knowledge) > 20
    assert len(meta.allowed_symptoms) > 0


def test_normalize_health_status():
    """Verify health status string normalization."""
    assert normalize_health_status("healthy") == "healthy"
    assert normalize_health_status("Healthy") == "healthy"
    assert normalize_health_status("good") == "healthy"
    assert normalize_health_status("normal") == "healthy"

    assert normalize_health_status("unhealthy") == "unhealthy"
    assert normalize_health_status("degraded") == "unhealthy"
    assert normalize_health_status("critical") == "unhealthy"
    assert normalize_health_status("possibly_unhealthy") == "unhealthy"
    assert normalize_health_status("") == "unhealthy"


def test_evaluate_final_dataset_metrics_perfect():
    """Verify metric calculations when predictions match ground truth exactly."""
    samples = [
        {"id": "s1", "species": "pothos", "status": "healthy", "symptoms": []},
        {"id": "s2", "species": "pothos", "status": "unhealthy", "symptoms": ["leaf_yellowing", "drooping"]},
        {"id": "s3", "species": "monstera", "status": "unhealthy", "symptoms": ["leaf_spots"]},
        {"id": "s4", "species": "monstera", "status": "healthy", "symptoms": []},
    ]
    preds = [
        {"id": "s1", "predicted_health_status": "healthy", "predicted_symptoms": []},
        {"id": "s2", "predicted_health_status": "unhealthy", "predicted_symptoms": ["leaf_yellowing", "drooping"]},
        {"id": "s3", "predicted_health_status": "unhealthy", "predicted_symptoms": ["leaf_spots"]},
        {"id": "s4", "predicted_health_status": "healthy", "predicted_symptoms": []},
    ]

    metrics = evaluate_final_dataset_metrics(samples, preds)

    # Health status: 2 TP, 2 TN, 0 FP, 0 FN -> 100%
    assert metrics["health_status"]["accuracy"] == 100.0
    assert metrics["health_status"]["f1"] == 100.0
    assert metrics["health_status"]["tp"] == 2
    assert metrics["health_status"]["tn"] == 2

    # Symptoms: perfect overlap
    assert metrics["symptoms"]["micro_f1"] == 100.0
    assert metrics["symptoms"]["macro_f1"] == 100.0

    # Per species breakdown
    assert "pothos" in metrics["by_species"]
    assert "monstera" in metrics["by_species"]
    assert metrics["by_species"]["pothos"]["health_status"]["accuracy"] == 100.0


def test_evaluate_final_dataset_metrics_mismatches():
    """Verify confusion matrix and metrics under false positive and false negative conditions."""
    samples = [
        {"id": "s1", "species": "aloe_vera", "status": "healthy", "symptoms": []},
        {"id": "s2", "species": "aloe_vera", "status": "unhealthy", "symptoms": ["drooping", "scorch"]},
    ]
    # Prediction: s1 is false alarm (FP), s2 misses scorch and status is healthy (FN)
    preds = [
        {"id": "s1", "predicted_health_status": "unhealthy", "predicted_symptoms": ["drooping"]},
        {"id": "s2", "predicted_health_status": "healthy", "predicted_symptoms": ["drooping"]},
    ]

    metrics = evaluate_final_dataset_metrics(samples, preds)

    assert metrics["health_status"]["accuracy"] == 0.0
    assert metrics["health_status"]["fp"] == 1
    assert metrics["health_status"]["fn"] == 1
    assert metrics["health_status"]["tp"] == 0
    assert metrics["health_status"]["tn"] == 0

    # Drooping: 1 TP on s2, 1 FP on s1
    assert metrics["by_symptom"]["drooping"]["tp"] == 1
    assert metrics["by_symptom"]["drooping"]["fp"] == 1
    # Scorch: 1 FN on s2
    assert metrics["by_symptom"]["scorch"]["fn"] == 1


def test_extract_json_from_text():
    """Verify robust JSON extraction from raw VLM strings."""
    raw_markdown = '```json\n{"health_status": "unhealthy", "symptoms": ["scorch"]}\n```'
    parsed = extract_json_from_text(raw_markdown)
    assert parsed["health_status"] == "unhealthy"
    assert parsed["symptoms"] == ["scorch"]

    raw_plain = 'Here is the output: {"health_status": "healthy", "symptoms": []} hope that helps.'
    parsed = extract_json_from_text(raw_plain)
    assert parsed["health_status"] == "healthy"
    assert parsed["symptoms"] == []

    with pytest.raises(ValueError):
        extract_json_from_text("no json here at all")


def test_predictor_caching_and_mock(tmp_path: Path):
    """Verify that FinalDatasetPredictor caches results into a JSONL sidecar and reads back."""
    cache_file = tmp_path / "test_preds.jsonl"
    predictor = FinalDatasetPredictor(predictions_file=cache_file, use_mock=True)

    dummy_img = tmp_path / "dummy.jpg"
    dummy_img.write_bytes(b"dummy image content bytes")

    dummy_sample = FinalDatasetSample(
        id="test_species/123",
        species="pothos",
        image_rel_path="images/pothos/dummy.jpg",
        status="healthy",
        symptoms=(),
        resolved_image_path=dummy_img,
    )

    meta = SpeciesMetadata(
        key="pothos",
        name="Pothos",
        knowledge="Pothos is resilient.",
        allowed_symptoms=("leaf_yellowing",),
    )

    # Predict sample
    res1 = predictor.predict_sample(dummy_sample, meta)
    assert res1["id"] == "test_species/123"
    assert res1["predicted_health_status"] == "healthy"
    assert cache_file.exists()

    # Re-instantiate predictor pointing at same file
    predictor2 = FinalDatasetPredictor(predictions_file=cache_file, use_mock=True)
    cached = predictor2.get_cached_prediction("test_species/123")
    assert cached is not None
    assert cached["id"] == "test_species/123"
    assert cached["predicted_health_status"] == "healthy"


def test_run_final_dataset_evaluation_mock(tmp_path: Path):
    """Integration test: run full final dataset evaluation workflow in mock mode."""
    config = EvaluationConfig()
    config.reports_dir = tmp_path / "reports"

    cache_file = tmp_path / "test_run_preds.jsonl"
    results_json = tmp_path / "results.json"

    res = run_final_dataset_evaluation(
        config=config,
        limit=10,
        predictions_file=cache_file,
        use_mock=True,
        results_json_path=results_json,
    )

    assert res.scope_name == "vlm"
    assert res.total_cases == 10
    assert res.status == "PASS"
    assert results_json.exists()

    with open(results_json, encoding="utf-8") as f:
        data = json.load(f)
    assert data["evaluated_samples"] == 10
    assert "health_status" in data
    assert "by_species" in data
