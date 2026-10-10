from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class AggregateError(RuntimeError):
    """Error raised when VLM observations cannot be aggregated."""


STRESS_SCORES: dict[str, int] = {
    "none": 0,
    "mild": 1,
    "moderate": 2,
    "severe": 3,
}

VALID_OBSERVATION_SEVERITIES = {"mild", "moderate", "severe"}
VALID_OBSERVATION_TYPES = {
    "leaf_yellowing",
    "brown_edges",
    "drooping",
    "curling",
    "visible_damage",
    "discoloration",
    "other",
}


@dataclass(frozen=True)
class RunDecision:
    """Derived health decision from one VLM observation run."""

    health_status: str
    observations: list[dict[str, str]]
    image_1_stress_level: str | None
    image_2_stress_level: str | None
    model_confidence: float | None
    raw_observation: dict[str, Any]


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from raw VLM text, including fenced JSON output."""

    stripped = text.strip()
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        stripped = fenced_match.group(1)
    else:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise AggregateError("VLM response does not contain a JSON object.")
        stripped = stripped[start : end + 1]

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise AggregateError(f"VLM response is not valid JSON: {error}") from error

    if not isinstance(parsed, dict):
        raise AggregateError("VLM response JSON must be an object.")
    return parsed


def parse_timezone_aware_iso(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp, requiring timezone information when present."""

    if not isinstance(value, str) or not value.strip():
        return None

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise AggregateError(f"Timestamp is not valid ISO-8601: {value}") from error

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AggregateError(f"Timestamp must include timezone information: {value}")
    return parsed


def serialize_timestamp(value: datetime) -> str:
    """Serialize a timezone-aware datetime without dropping its offset."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise AggregateError("Timestamp must include timezone information.")
    return value.isoformat(timespec="seconds")


def read_json_object(path: Path) -> dict[str, Any] | None:
    """Read a JSON metadata object when it exists."""

    if not path.exists():
        return None

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise AggregateError(f"Metadata is not valid JSON: {path}") from error

    if not isinstance(parsed, dict):
        return None
    return parsed


def read_captured_at(metadata_path: Path) -> str | None:
    """Read a timezone-aware captured_at value from one metadata file."""

    metadata = read_json_object(metadata_path)
    if metadata is None:
        return None

    captured_at = parse_timezone_aware_iso(metadata.get("captured_at"))
    if captured_at is None:
        return None
    return serialize_timestamp(captured_at)


def source_image_metadata_path(processed_metadata_path: Path) -> Path | None:
    """Find raw capture metadata referenced by processed-image metadata."""

    metadata = read_json_object(processed_metadata_path)
    if metadata is None:
        return None

    source_image_path = metadata.get("source_image_path")
    if not isinstance(source_image_path, str) or not source_image_path.strip():
        return None

    return Path(source_image_path).with_suffix(".json")


def capture_timestamp_for_image(image_path: Path) -> str | None:
    """Return the capture timestamp for an image if sidecar metadata provides it."""

    metadata_path = image_path.with_suffix(".json")

    direct_timestamp = read_captured_at(metadata_path)
    if direct_timestamp is not None:
        return direct_timestamp

    source_metadata_path = source_image_metadata_path(metadata_path)
    if source_metadata_path is None:
        return None
    return read_captured_at(source_metadata_path)


def assessment_output_timestamp(
    current_image_path: Path,
    assessed_at: datetime | None = None,
) -> str:
    """Use current-image capture time when available, otherwise inference time."""

    capture_timestamp = capture_timestamp_for_image(current_image_path)
    if capture_timestamp is not None:
        return capture_timestamp

    assessed_at = assessed_at or datetime.now().astimezone()
    return serialize_timestamp(assessed_at)


def normalize_stress_level(value: object) -> str | None:
    """Normalize one visible_stress_level value from the VLM output."""

    if not isinstance(value, str):
        return None

    normalized = value.strip().lower()
    if normalized in STRESS_SCORES or normalized == "cannot_tell":
        return normalized
    return None


def stress_score(stress_level: str | None) -> int | None:
    """Convert visible stress level to an ordinal score."""

    if stress_level is None or stress_level == "cannot_tell":
        return None
    return STRESS_SCORES.get(stress_level)


def clamp_model_confidence(value: object) -> float | None:
    """Normalize the model's own stated confidence when present."""

    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def observation_stress_level(observation: dict[str, Any], key: str) -> str | None:
    """Read visible_stress_level from one image observation object."""

    section = observation.get(key)
    if not isinstance(section, dict):
        return None
    return normalize_stress_level(section.get("visible_stress_level"))


def derive_run_decision(observation: dict[str, Any]) -> RunDecision:
    """Derive health status and current observations from one VLM run."""

    image_1_stress = observation_stress_level(observation, "image_1_observation")
    image_2_stress = observation_stress_level(observation, "image_2_observation")
    image_2_score = stress_score(image_2_stress)

    if image_2_score is None:
        health_status = "possible_unhealthy"
    elif image_2_score == 0:
        health_status = "healthy"
    elif image_2_score == 1:
        health_status = "possible_unhealthy"
    else:
        health_status = "unhealthy"

    return RunDecision(
        health_status=health_status,
        observations=clean_current_observations(observation, image_2_stress),
        image_1_stress_level=image_1_stress,
        image_2_stress_level=image_2_stress,
        model_confidence=clamp_model_confidence(observation.get("model_confidence")),
        raw_observation=observation,
    )


def majority_health_status(decisions: list[RunDecision]) -> str:
    """Return the winning health status, preferring caution on ties."""

    counts = Counter(decision.health_status for decision in decisions)
    if not counts:
        return "possible_unhealthy"

    highest_count = max(counts.values())
    winners = [status for status, count in counts.items() if count == highest_count]
    if len(winners) == 1:
        return winners[0]

    tie_order = ["unhealthy", "possible_unhealthy", "healthy"]
    for status in tie_order:
        if status in winners:
            return status
    return winners[0]


def clean_text_field(value: object) -> str:
    """Normalize optional VLM text fields for the compact output contract."""

    if isinstance(value, str) and value.strip():
        text = value.strip()
        text = re.sub(r"\b[Ll]eaves in image[_ ]?2\b", "Current plant leaves", text)
        text = re.sub(r"\b[Ii]mage[_ ]?2\b", "current plant state", text)
        return text
    return "cannot_tell"


def normalize_observation_type(value: object) -> str | None:
    """Normalize a VLM observation type into a compact snake_case label."""

    if not isinstance(value, str) or not value.strip():
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if normalized == "yellowing":
        return "leaf_yellowing"
    if normalized in {"brown_tips", "browning_edges"}:
        return "brown_edges"
    if normalized in VALID_OBSERVATION_TYPES:
        return normalized
    return None


def observation_types_from_text(*values: object) -> list[str]:
    """Extract known symptom types from VLM type and description text."""

    text = " ".join(value for value in values if isinstance(value, str)).lower()
    symptom_patterns = [
        ("leaf_yellowing", r"\byellow|yellowing\b"),
        ("brown_edges", r"\bbrown|browning|brown_edges|brown_tips\b"),
        ("drooping", r"\bdroop|drooping|limp|collapsed\b"),
        ("curling", r"\bcurl|curling\b"),
        ("visible_damage", r"\bdamage|damaged|tear|tears|spot|spots|dry\b"),
        ("discoloration", r"\bdiscolor|discoloration\b"),
    ]
    matches = [
        symptom_type
        for symptom_type, pattern in symptom_patterns
        if re.search(pattern, text)
    ]
    return list(dict.fromkeys(matches))


def normalize_observation_severity(value: object) -> str | None:
    """Normalize one per-observation severity value."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in VALID_OBSERVATION_SEVERITIES:
        return normalized
    return None


def severity_from_stress_level(stress_level: str | None) -> str:
    """Map image-level visible stress into observation-level severity."""

    if stress_level in VALID_OBSERVATION_SEVERITIES:
        return stress_level
    if stress_level == "none":
        return "mild"
    return "moderate"


def clean_current_observations(
    observation: dict[str, Any],
    image_2_stress: str | None,
) -> list[dict[str, str]]:
    """Return Image 2 health-concern observations for the final output."""

    explicit_observations = observation.get("current_observations")
    if isinstance(explicit_observations, list):
        cleaned = []
        for item in explicit_observations:
            if not isinstance(item, dict):
                continue
            severity = normalize_observation_severity(item.get("severity"))
            description = clean_text_field(item.get("description"))
            if not severity or description == "cannot_tell":
                continue
            observation_types = observation_types_from_text(item.get("type"), description)
            observation_type = normalize_observation_type(item.get("type"))
            if observation_type and observation_type not in observation_types:
                observation_types.insert(0, observation_type)
            for observation_type in observation_types:
                cleaned.append(
                    {
                        "type": observation_type,
                        "severity": severity,
                        "description": description,
                    }
                )
        if cleaned or image_2_stress == "none":
            return cleaned

    section = observation.get("image_2_observation")
    if not isinstance(section, dict):
        section = {}

    if image_2_stress == "none":
        return []

    severity = severity_from_stress_level(image_2_stress)
    fallback: list[dict[str, str]] = []
    for observation_type, field in [
        ("leaf_posture", "leaf_posture"),
        ("leaf_color", "leaf_color"),
        ("visible_damage", "visible_damage"),
    ]:
        description = clean_text_field(section.get(field))
        if description != "cannot_tell":
            fallback.append(
                {
                    "type": observation_type,
                    "severity": severity,
                    "description": description,
                }
            )
    return fallback


def severity_rank(severity: str) -> int:
    """Sort observation severities from mild to severe."""

    return {"mild": 1, "moderate": 2, "severe": 3}.get(severity, 0)


def consensus_observations(decisions: list[RunDecision]) -> list[dict[str, str]]:
    """Merge per-run observations into one compact observation list."""

    grouped: dict[str, list[dict[str, str]]] = {}
    for decision in decisions:
        for observation in decision.observations:
            grouped.setdefault(observation["type"], []).append(observation)

    merged = []
    for observation_type, items in grouped.items():
        severity = max(
            (item["severity"] for item in items),
            key=severity_rank,
        )
        description = max(
            (item["description"] for item in items),
            key=len,
        )
        merged.append(
            {
                "type": observation_type,
                "severity": severity,
                "description": description,
            }
        )

    return sorted(
        merged,
        key=lambda item: (-severity_rank(item["severity"]), item["type"]),
    )


def aggregate_observations(
    observations: list[dict[str, Any]],
    *,
    plant_id: str,
    species: str,
    timestamp: str | None = None,
    image_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate repeated VLM observations into the plant health output shape."""

    if not observations:
        raise AggregateError("At least one observation is required.")
    if not plant_id.strip():
        raise AggregateError("plant_id is required.")
    if not species.strip():
        raise AggregateError("species is required.")

    parsed_timestamp = parse_timezone_aware_iso(timestamp)
    if parsed_timestamp is None:
        parsed_timestamp = datetime.now().astimezone()

    decisions = [derive_run_decision(observation) for observation in observations]
    health_status = majority_health_status(decisions)
    matching = [
        decision for decision in decisions if decision.health_status == health_status
    ]
    agreement = len(matching) / len(decisions)
    model_confidences = [
        decision.model_confidence
        for decision in decisions
        if decision.model_confidence is not None
    ]

    return {
        "plant_id": plant_id.strip(),
        "species": species.strip(),
        "timestamp": serialize_timestamp(parsed_timestamp),
        "health_status": health_status,
        "consensus": {
            "agreement": round(agreement, 3),
            "runs": len(decisions),
            "model_stated_average": (
                round(sum(model_confidences) / len(model_confidences), 3)
                if model_confidences
                else None
            ),
        },
        "observations": consensus_observations(matching),
        "image_refs": image_refs or [],
    }
