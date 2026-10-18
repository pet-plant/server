"""Inference predictor for final dataset evaluation.

Queries the Visual Language Model (VLM) for plant condition assessment:
- Extracts botanical knowledge from species metadata
- Prompts the model for structured JSON output (`health_status` and `symptoms`)
- Handles model responses and json extraction
- Checkpoints predictions to `evaluation/reports/final_predictions.jsonl`
- Supports resuming from cached predictions and running with sample limits
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Sequence

from evaluation.vlm.final_dataset import FinalDatasetSample, SpeciesMetadata

logger = logging.getLogger(__name__)

DEFAULT_PREDICTIONS_PATH = (
    Path(__file__).resolve().parent.parent / "reports" / "final_predictions.jsonl"
)


def extract_json_from_text(raw_text: str) -> dict[str, Any]:
    """Extract a JSON object from text, handling markdown fences and raw JSON."""
    stripped = raw_text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        try:
            return json.loads(fenced_match.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*?\}", stripped, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as err:
        raise ValueError(f"Could not parse valid JSON from VLM output: {raw_text[:200]}") from err


def build_condition_prompt(
    species_meta: SpeciesMetadata | None,
    species_name: str,
) -> str:
    """Build the condition evaluation prompt for the VLM given botanical knowledge."""
    knowledge = species_meta.knowledge if species_meta else ""
    allowed_tags = list(species_meta.allowed_symptoms) if species_meta else []

    allowed_tags_str = ", ".join(f'"{t}"' for t in allowed_tags) if allowed_tags else "any visible symptoms"

    return (
        f"You are a botanical visual expert evaluating the health of a houseplant.\n"
        f"Plant Species: {species_name}\n\n"
        f"Species Care Knowledge:\n{knowledge}\n\n"
        f"Task:\n"
        f"1. Evaluate if this plant photo shows a healthy or unhealthy plant.\n"
        f"2. Identify any visible symptom tags strictly from this allowed list:\n"
        f"   [{allowed_tags_str}]\n"
        f"   (If the plant is healthy or has no visible problems, symptoms must be an empty list []).\n\n"
        f"Output Requirement:\n"
        f"Return ONLY a JSON object in this exact format with no extra markdown or explanations outside the JSON:\n"
        f'{{"health_status": "healthy" | "unhealthy", "symptoms": ["tag1", "tag2"], "explanation": "brief reasoning"}}\n'
    )


class FinalDatasetPredictor:
    """Manages VLM prediction runs with incremental disk caching."""

    def __init__(
        self,
        predictions_file: Path | str | None = None,
        backend: Any | None = None,
        use_mock: bool = False,
    ) -> None:
        self.use_mock = use_mock
        if use_mock and predictions_file is None:
            self.predictions_file = Path("/dev/null")
        else:
            self.predictions_file = Path(predictions_file) if predictions_file else DEFAULT_PREDICTIONS_PATH
        self.backend = backend
        self._cached_predictions: dict[str, dict[str, Any]] = {}
        if self.predictions_file != Path("/dev/null"):
            self._load_cached_predictions()

    def _load_cached_predictions(self) -> None:
        """Load already computed predictions from the output JSONL file."""
        if not self.predictions_file.exists():
            return
        try:
            with open(self.predictions_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    rec_id = str(rec.get("id") or "")
                    if rec_id:
                        self._cached_predictions[rec_id] = rec
        except Exception as err:
            logger.warning("Failed loading cached predictions from %s: %s", self.predictions_file, err)

    def _append_prediction(self, record: dict[str, Any]) -> None:
        """Append a prediction record to the JSONL cache file."""
        self.predictions_file.parent.mkdir(parents=True, exist_ok=True)
        rec_id = str(record.get("id") or "")
        self._cached_predictions[rec_id] = record
        with open(self.predictions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_cached_prediction(self, sample_id: str) -> dict[str, Any] | None:
        """Return cached prediction for sample_id if available."""
        return self._cached_predictions.get(str(sample_id))

    def _get_vlm_backend(self) -> Any:
        """Obtain VLM backend on demand."""
        if self.backend is not None:
            return self.backend
        from mlops.assessment.backends import get_vlm_backend

        self.backend = get_vlm_backend()
        return self.backend

    def predict_sample(
        self,
        sample: FinalDatasetSample,
        species_meta: SpeciesMetadata | None,
        force_recompute: bool = False,
    ) -> dict[str, Any]:
        """Predict health_status and symptoms for a single sample."""
        sample_id = sample.id

        if not force_recompute and sample_id in self._cached_predictions:
            return self._cached_predictions[sample_id]

        if not sample.resolved_image_path or not sample.resolved_image_path.exists():
            record = {
                "id": sample_id,
                "species": sample.species,
                "predicted_health_status": "unhealthy",
                "predicted_symptoms": [],
                "error": "Image file not found on disk",
                "latency_ms": 0.0,
            }
            self._append_prediction(record)
            return record

        with open(sample.resolved_image_path, "rb") as img_f:
            image_bytes = img_f.read()

        prompt = build_condition_prompt(
            species_meta=species_meta,
            species_name=species_meta.name if species_meta else sample.species,
        )

        start_time = time.perf_counter()

        if self.use_mock:
            # Deterministic simulation for tests/mocking
            latency = 15.0
            # Default to sample status if mock, or mock baseline
            status = getattr(sample, "status", "healthy")
            symptoms = list(getattr(sample, "symptoms", []))
            record = {
                "id": sample_id,
                "species": sample.species,
                "predicted_health_status": status,
                "predicted_symptoms": symptoms,
                "explanation": "Simulated mock inference",
                "latency_ms": latency,
            }
            self._append_prediction(record)
            return record

        backend = self._get_vlm_backend()
        try:
            raw_output = backend.generate(
                prompt=prompt,
                images=[image_bytes],
                model="internvl3_5-2b",
                temperature=0.1,
                max_new_tokens=512,
            )
            parsed = extract_json_from_text(raw_output)
            pred_status = str(parsed.get("health_status", "healthy")).strip().lower()
            pred_symptoms = list(parsed.get("symptoms", []))

            # Filter or sanitize symptoms against allowed list
            if species_meta and species_meta.allowed_symptoms:
                allowed_set = set(species_meta.allowed_symptoms)
                pred_symptoms = [s for s in pred_symptoms if s in allowed_set]

            latency = round((time.perf_counter() - start_time) * 1000.0, 2)
            record = {
                "id": sample_id,
                "species": sample.species,
                "predicted_health_status": pred_status,
                "predicted_symptoms": pred_symptoms,
                "explanation": parsed.get("explanation", ""),
                "latency_ms": latency,
            }
        except Exception as err:
            logger.error("VLM inference failed on sample %s: %s", sample_id, err)
            latency = round((time.perf_counter() - start_time) * 1000.0, 2)
            record = {
                "id": sample_id,
                "species": sample.species,
                "predicted_health_status": "unhealthy",
                "predicted_symptoms": [],
                "error": str(err),
                "latency_ms": latency,
            }

        self._append_prediction(record)
        return record

    def predict_batch(
        self,
        samples: Sequence[FinalDatasetSample],
        species_meta_map: dict[str, SpeciesMetadata],
        limit: int | None = None,
        force_recompute: bool = False,
        progress_callback: Any | None = None,
    ) -> list[dict[str, Any]]:
        """Run predictions across a batch of samples."""
        to_run = samples[:limit] if limit else samples
        results: list[dict[str, Any]] = []

        total = len(to_run)
        for idx, sample in enumerate(to_run, 1):
            meta = species_meta_map.get(sample.species)
            pred = self.predict_sample(sample, meta, force_recompute=force_recompute)
            results.append(pred)

            if progress_callback:
                progress_callback(idx, total, sample, pred)

        return results
