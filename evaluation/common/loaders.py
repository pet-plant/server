"""Dataset manifest loaders with strict JSON schema validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError


class ManifestValidationError(ValueError):
    """Raised when an evaluation dataset manifest fails schema validation."""


END_TO_END_MANIFEST_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["version", "scope", "scenarios"],
    "properties": {
        "version": {"type": "string"},
        "scope": {"const": "end_to_end"},
        "description": {"type": "string"},
        "scenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "scenario_file", "expected_file", "mandatory_criteria"],
                "properties": {
                    "name": {"type": "string"},
                    "scenario_file": {"type": "string"},
                    "expected_file": {"type": "string"},
                    "mandatory_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    },
}


# --- Typed Data Classes ---

@dataclass
class EndToEndScenarioCase:
    name: str
    scenario_file: str
    expected_file: str
    mandatory_criteria: list[str]


# --- Loaders ---

def _validate(data: dict[str, Any], schema: dict[str, Any], manifest_path: Path) -> None:
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.json_path)
    if errors:
        first = errors[0]
        msg = f"Manifest {manifest_path.name} failed validation at {first.json_path}: {first.message}"
        raise ManifestValidationError(msg)


def load_end_to_end_manifest(manifest_path: Path) -> list[EndToEndScenarioCase]:
    """Load and validate the end-to-end scenario evaluation manifest."""
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    _validate(data, END_TO_END_MANIFEST_SCHEMA, manifest_path)

    cases: list[EndToEndScenarioCase] = []
    for sc in data["scenarios"]:
        cases.append(
            EndToEndScenarioCase(
                name=sc["name"],
                scenario_file=sc["scenario_file"],
                expected_file=sc["expected_file"],
                mandatory_criteria=list(sc.get("mandatory_criteria", [])),
            )
        )
    return cases
