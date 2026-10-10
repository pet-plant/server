from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from assessment.aggregate import (
    AggregateError,
    aggregate_observations,
    assessment_output_timestamp,
    extract_json_object,
)
from assessment.probes_2 import DEFAULT_KNOWLEDGE_FILE, ProbeError, build_probe_package

ASSESSMENT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = ASSESSMENT_DIR / "models" / "internvl3_5-2b"


class AssessmentPipelineError(RuntimeError):
    """Error raised when the assessment pipeline cannot complete."""

PROJECT_ROOT = ASSESSMENT_DIR.parent.parent

def resolve_image_path(image_path: str | Path) -> Path:
    path = Path(image_path)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    path = path.resolve()

    if not path.is_file():
        raise AssessmentPipelineError(
            f"Image does not exist: {path}"
        )

    return path

def resolve_knowledge_path(knowledge_file: str | Path | None) -> Path | None:
    if knowledge_file is None:
        return None

    path = Path(knowledge_file)

    if path.is_absolute():
        resolved = path.resolve()
    else:
        # รองรับ path เดิมจาก Database:
        # assessment/knowledge/peace_lily.txt
        parts = path.parts

        if parts and parts[0].lower() == "assessment":
            resolved = (PROJECT_ROOT / "src" / path).resolve()
        else:
            resolved = (ASSESSMENT_DIR / path).resolve()

    if not resolved.is_file():
        raise AssessmentPipelineError(
            f"Knowledge file does not exist: {resolved}"
        )

    return resolved

@dataclass(frozen=True)
class PlantContext:
    """Plant metadata supplied by System Manager without requiring database access."""

    plant_id: str = "plant_001"
    species: str | None = None
    knowledge_file: Path | None = DEFAULT_KNOWLEDGE_FILE


def normalize_plant_context(plant_context: PlantContext | Mapping[str, Any] | None) -> PlantContext:
    """Normalize System Manager plant context into a typed local object."""

    if plant_context is None:
        return PlantContext()
    if isinstance(plant_context, PlantContext):
        return plant_context

    knowledge_file = plant_context.get("knowledge_file", DEFAULT_KNOWLEDGE_FILE)
    if isinstance(knowledge_file, str):
        knowledge_file = Path(knowledge_file)

    species = plant_context.get("species")
    return PlantContext(
        plant_id=str(plant_context.get("plant_id", "plant_001")).strip() or "plant_001",
        species=str(species).strip() if species is not None and str(species).strip() else None,
        knowledge_file=knowledge_file,
    )


def image_ref(image_path: Path) -> str:
    """Format an image path as the file reference used in the final JSON output."""

    normalized = image_path.as_posix()
    if normalized.startswith("/"):
        return f"file://{normalized}"
    return f"file:///{normalized}"


def run_assessment(
    previous_image_path: str | Path,
    current_image_path: str | Path,
    plant_context: PlantContext | Mapping[str, Any] | None = None,
    *,
    probe: str = "plant_observation_pair",
    model_path: str | Path = DEFAULT_MODEL_PATH,
    max_new_tokens: int = 520,
    runs: int = 5,
    temperature: float = 0.3,
    include_runs: bool = False,
) -> dict[str, Any]:
    """Compare previous/current plant images and return the clean assessment JSON.

    This is the System Manager-facing wrapper around the existing Assessment V2 PoC.
    It does not read or write database state; all plant identity/context is supplied
    by the caller through `plant_context`.
    """

    previous_image_path = resolve_image_path(previous_image_path)
    current_image_path = resolve_image_path(current_image_path)
    context = normalize_plant_context(plant_context)
    context = PlantContext(
        plant_id=context.plant_id,
        species=context.species,
        knowledge_file=resolve_knowledge_path(context.knowledge_file)
    )

    try:
        if runs < 1:
            raise AssessmentPipelineError("runs must be at least 1.")
        if temperature < 0:
            raise AssessmentPipelineError("temperature must be 0 or greater.")

        from assessment.vlm_2 import VLMConfig, load_vlm, run_probe_package

        package = build_probe_package(
            probe,
            previous_image_path,
            current_image_path,
            context.knowledge_file,
        )
        species = context.species or package.species

        config = VLMConfig(
            model_path=Path(model_path),
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
        loaded_vlm = load_vlm(config)

        raw_responses: list[str] = []
        observations: list[dict[str, Any]] = []
        for _ in range(runs):
            response = run_probe_package(package, loaded_vlm, config)
            raw_responses.append(response)
            observations.append(extract_json_object(response))

        result = aggregate_observations(
            observations,
            plant_id=context.plant_id,
            species=species,
            timestamp=assessment_output_timestamp(current_image_path),
            image_refs=[image_ref(previous_image_path), image_ref(current_image_path)],
        )
    except AssessmentPipelineError:
        raise
    except (ProbeError, AggregateError, ImportError, RuntimeError) as error:
        raise AssessmentPipelineError(str(error)) from error

    if include_runs:
        result["raw_runs"] = raw_responses
    return result


def parse_args() -> argparse.Namespace:
    """Read CLI arguments for manual assessment-pipeline testing."""

    parser = argparse.ArgumentParser(description="Run the PoC two-image assessment pipeline.")
    parser.add_argument("--previous-image", type=Path, required=True)
    parser.add_argument("--current-image", type=Path, required=True)
    parser.add_argument("--plant-id", default="plant_001")
    parser.add_argument("--species", default=None)
    parser.add_argument("--knowledge-file", type=Path, default=DEFAULT_KNOWLEDGE_FILE)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--max-new-tokens", type=int, default=520)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--include-runs", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m assessment.run_assessment`."""

    args = parse_args()
    context = PlantContext(
        plant_id=args.plant_id,
        species=args.species,
        knowledge_file=args.knowledge_file,
    )

    try:
        result = run_assessment(
            args.previous_image,
            args.current_image,
            context,
            model_path=args.model_path,
            max_new_tokens=args.max_new_tokens,
            runs=args.runs,
            temperature=args.temperature,
            include_runs=args.include_runs,
        )
    except AssessmentPipelineError as error:
        print(f"Assessment pipeline error: {error}")
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
