from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


class ProbeError(RuntimeError):
    """Error raised when a probe package cannot be built."""


@dataclass(frozen=True)
class ProbeDefinition:
    """A single-image visual observation task for the VLM."""

    key: str
    probe_id: str
    species: str
    crop: str
    focus: str


@dataclass(frozen=True)
class ProbePackage:
    """VLM-ready package for one image and one observation prompt."""

    probe_id: str
    species: str
    crop: str
    image_path: str
    prompt: str
    expected_output: dict[str, object]


PLANT_OBSERVATION_PROBE = ProbeDefinition(
    key="plant_observation",
    probe_id="spath.visual_observation.whole_plant",
    species="Spathiphyllum wallisii",
    crop="whole_plant",
    focus=(
        "Describe the visible condition of this plant from a single image. "
        "Focus on leaf posture, leaf color, visible leaf damage, pot or soil "
        "context if visible, and image quality."
    ),
)

PROBES: dict[str, ProbeDefinition] = {
    PLANT_OBSERVATION_PROBE.key: PLANT_OBSERVATION_PROBE,
}

EXPECTED_OUTPUT: dict[str, object] = {
    "image_description": "one or two sentences describing the whole visible plant",
    "leaf_posture": "description of whether leaves look upright, relaxed, drooping, curled, or collapsed",
    "leaf_color": "description of visible green/yellow/brown color patterns",
    "visible_damage": "description of visible browning, dry edges, tears, spots, or none",
    "soil_or_pot_context": "description of visible pot/soil context or cannot_tell",
    "image_quality": "clear | slightly_blurry | blurry | too_dark | too_bright | cannot_tell",
    "visible_stress_level": "none | mild | moderate | severe | cannot_tell",
    "evidence": "one sentence naming the strongest visible cues",
}


def get_probe(probe_key: str) -> ProbeDefinition:
    """Return a probe definition by short key."""

    try:
        return PROBES[probe_key]
    except KeyError as error:
        available = ", ".join(sorted(PROBES))
        raise ProbeError(f"Unknown probe '{probe_key}'. Available probes: {available}") from error


def build_probe_prompt(probe: ProbeDefinition) -> str:
    """Build the exact single-image observation prompt sent to the VLM."""

    return f"""You inspect one photograph of one plant and describe only what is visible.

Image input:
- Image 1 = current plant observation

Task:
{probe.focus}

Important:
- Do not compare this image with any other image.
- Do not diagnose the biological cause.
- Do not give care advice.
- Do not claim anything that is not visible in the image.
- If a region is unclear, occluded, or outside the image, say cannot_tell for that field.

Return ONLY valid JSON in exactly this format:
{{
  "image_description": "one or two sentences describing the whole visible plant",
  "leaf_posture": "description of whether leaves look upright, relaxed, drooping, curled, or collapsed",
  "leaf_color": "description of visible green/yellow/brown color patterns",
  "visible_damage": "description of visible browning, dry edges, tears, spots, or none",
  "soil_or_pot_context": "description of visible pot/soil context or cannot_tell",
  "image_quality": "clear | slightly_blurry | blurry | too_dark | too_bright | cannot_tell",
  "visible_stress_level": "none | mild | moderate | severe | cannot_tell",
  "evidence": "one sentence naming the strongest visible cues"
}}

Field rules:
- image_description should describe the overall visible plant, not the room.
- leaf_posture should mention whether the leaves are upright, relaxed, drooping, curled, or collapsed.
- leaf_color should mention visible color patterns only.
- visible_damage should mention visible damage only, such as brown tips, dry edges, yellowing, tears, or spots.
- soil_or_pot_context should describe the visible pot or soil only if visible.
- image_quality should choose exactly one value from: clear, slightly_blurry, blurry, too_dark, too_bright, cannot_tell.
- visible_stress_level should choose exactly one value from: none, mild, moderate, severe, cannot_tell.
- evidence should be one concise sentence grounded in visible cues."""


def build_probe_package(probe_key: str, image_path: Path) -> ProbePackage:
    """Build a VLM-ready probe package for one image."""

    probe = get_probe(probe_key)
    if not image_path.exists():
        raise ProbeError(f"Image does not exist: {image_path}")

    return ProbePackage(
        probe_id=probe.probe_id,
        species=probe.species,
        crop=probe.crop,
        image_path=str(image_path),
        prompt=build_probe_prompt(probe),
        expected_output=EXPECTED_OUTPUT,
    )


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for probe package generation."""

    parser = argparse.ArgumentParser(description="Build a VLM-ready single-image observation package.")
    parser.add_argument("--probe", default=PLANT_OBSERVATION_PROBE.key, choices=sorted(PROBES))
    parser.add_argument("--image", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m assessment.probes_1`."""

    args = parse_args()

    try:
        package = build_probe_package(args.probe, args.image)
    except ProbeError as error:
        print(f"Probe error: {error}")
        return 1

    print(json.dumps(asdict(package), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
