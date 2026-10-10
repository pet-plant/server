from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


class ProbeError(RuntimeError):
    """Error raised when a two-image probe package cannot be built."""


@dataclass(frozen=True)
class ProbeDefinition:
    """A two-image visual observation task for the VLM."""

    key: str
    probe_id: str
    species: str
    crop: str
    focus: str


@dataclass(frozen=True)
class ProbePackage:
    """VLM-ready package for two images and one observation prompt."""

    probe_id: str
    species: str
    crop: str
    image_1_path: str
    image_2_path: str
    prompt: str
    expected_output: dict[str, object]


TWO_IMAGE_OBSERVATION_PROBE = ProbeDefinition(
    key="plant_observation_pair",
    probe_id="spath.visual_observation_pair.whole_plant",
    species="Spathiphyllum wallisii",
    crop="whole_plant",
    focus=(
        "Describe both plant images separately, then describe only the visible "
        "differences between them. Focus on leaf posture, leaf color, visible "
        "damage, pot or soil context if visible, and any other visible cues."
    ),
)

PROBES: dict[str, ProbeDefinition] = {
    TWO_IMAGE_OBSERVATION_PROBE.key: TWO_IMAGE_OBSERVATION_PROBE,
}

EXPECTED_OUTPUT: dict[str, object] = {
    "image_1_observation": {
        "image_description": "one or two sentences describing image 1",
        "leaf_posture": "visible posture in image 1",
        "leaf_color": "visible color patterns in image 1",
        "visible_damage": "visible damage in image 1",
        "visible_stress_level": "none | mild | moderate | severe | cannot_tell",
    },
    "image_2_observation": {
        "image_description": "one or two sentences describing image 2",
        "leaf_posture": "visible posture in image 2",
        "leaf_color": "visible color patterns in image 2",
        "visible_damage": "visible damage in image 2",
        "visible_stress_level": "none | mild | moderate | severe | cannot_tell",
    },
    "visible_differences": [
        "short visible difference between image 1 and image 2",
    ],
    "current_observations": [
        {
            "type": "one of: leaf_yellowing, brown_edges, drooping, curling, visible_damage, discoloration, other",
            "severity": "mild | moderate | severe",
            "description": "short visible description from image 2",
        }
    ],
    "comparison_summary": "short description of how the visible plant condition differs",
    "model_confidence": "number from 0.0 to 1.0",
}

ASSESSMENT_DIR = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_FILE = ASSESSMENT_DIR / "knowledge" / "peace_lily.txt"


def get_probe(probe_key: str) -> ProbeDefinition:
    """Return a probe definition by short key."""

    try:
        return PROBES[probe_key]
    except KeyError as error:
        available = ", ".join(sorted(PROBES))
        raise ProbeError(f"Unknown probe '{probe_key}'. Available probes: {available}") from error


def load_plant_knowledge(knowledge_file: Path | None) -> str:
    """Load optional species knowledge that helps the VLM interpret visible traits."""

    if knowledge_file is None:
        return ""
    if not knowledge_file.exists():
        raise ProbeError(f"Knowledge file does not exist: {knowledge_file}")

    knowledge = knowledge_file.read_text(encoding="utf-8").strip()
    if not knowledge:
        raise ProbeError(f"Knowledge file is empty: {knowledge_file}")
    return knowledge


def plant_knowledge_section(plant_knowledge: str) -> str:
    """Build the optional plant-knowledge prompt section."""

    if not plant_knowledge:
        return ""
    return f"""
Plant knowledge:
{plant_knowledge}
"""


def build_probe_prompt(probe: ProbeDefinition, plant_knowledge: str = "") -> str:
    """Build the exact two-image observation prompt sent to the VLM."""

    return f"""You inspect two photographs of the same plant and describe only what is visible.
{plant_knowledge_section(plant_knowledge)}

Image input:
- Image 1 = first plant observation
- Image 2 = second plant observation

Task:
{probe.focus}

Important:
- Describe Image 1 and Image 2 separately before describing differences.
- Use plant knowledge only to interpret visible traits for the stated species.
- Do not diagnose the biological cause.
- Do not give care advice.
- Do not infer dates, watering, disease, or causes from the image.
- Do not claim anything that is not visible.
- If a region is unclear, occluded, or outside an image, say cannot_tell for that field.

Return ONLY valid JSON in exactly this format:
{{
  "image_1_observation": {{
    "image_description": "one or two sentences describing image 1",
    "leaf_posture": "visible posture in image 1",
    "leaf_color": "visible color patterns in image 1",
    "visible_damage": "visible damage in image 1",
    "visible_stress_level": "none | mild | moderate | severe | cannot_tell"
  }},
  "image_2_observation": {{
    "image_description": "one or two sentences describing image 2",
    "leaf_posture": "visible posture in image 2",
    "leaf_color": "visible color patterns in image 2",
    "visible_damage": "visible damage in image 2",
    "visible_stress_level": "none | mild | moderate | severe | cannot_tell"
  }},
  "visible_differences": [
    "short visible difference between image 1 and image 2"
  ],
   "current_observations": [
    {{
      "type": "leaf_yellowing",
      "severity": "mild",
      "description": "Yellow discoloration is visible on parts of the leaves."
    }},
    {{
      "type": "brown_edges",
      "severity": "mild",
      "description": "Brown discoloration is visible along some leaf edges."
    }}
  ],
  "comparison_summary": "short description of how the visible plant condition differs",
  "model_confidence": 0.0
}}

Field rules:
- Use separate observations for Image 1 and Image 2.
- visible_stress_level must be exactly one of: none, mild, moderate, severe, cannot_tell.
- Use visible_stress_level "none" when the plant appears visually healthy, with upright or naturally relaxed leaves, mostly even green color, and no clear visible damage.
- Use visible_stress_level "mild" when there are small visible concerns, such as slight drooping, slight yellowing, minor brown tips, or limited edge damage, while most leaves still look healthy.
- Use visible_stress_level "moderate" when stress is clearly visible across multiple leaves, such as noticeable drooping, yellowing, curling, browning edges, dry tips, or a generally weakened posture.
- Use visible_stress_level "severe" when the plant appears strongly stressed, with collapsed or heavily drooping leaves, widespread yellow/brown areas, extensive dry or dead-looking tissue, or severe visible damage.
- Use visible_stress_level "cannot_tell" when the plant condition cannot be judged because the plant is unclear, heavily occluded, too cropped, or the relevant regions are not visible.
- visible_differences should list concrete visual differences only.
- current_observations should describe visible health concerns in Image 2 only.
- current_observations should be an empty list when Image 2 looks healthy or when no concrete concern is visible.
- current_observations severity must be exactly one of: mild, moderate, severe.
- current_observations type must be exactly one of: leaf_yellowing, brown_edges, drooping, curling, visible_damage, discoloration, other.
- Use one current_observations item per visible symptom. Do not combine symptoms into one type such as yellowing_brown_edges.
- Each current_observations item must describe only the symptom specified by its type.
- Write a distinct, symptom-specific description for each observation.
- For leaf_yellowing, describe only the visible yellow discoloration, including its location and extent when identifiable.
- For brown_edges, describe only the visible brown discoloration along leaf edges or tips.
- For drooping, describe only the visible downward bending or hanging of leaves.
- For curling, describe only the visible curling or rolling of leaves.
- Do not mention other symptom types in the same description.
- Do not reuse the same description across different observation types.
- Describe the visible evidence rather than making general statements about plant stress.
- If the location or extent of a symptom is unclear, do not invent those details.
- The JSON examples are illustrative only. Include a symptom only when it is clearly visible in Image 2; do not copy example observations.
- Do not copy the list of allowed types into the type field.
- comparison_summary should be short and grounded in visible cues.
- model_confidence should be your own stated confidence from 0.0 to 1.0 that the visual observations are correct. This value will be recorded but not trusted as the main confidence."""


def build_probe_package(
    probe_key: str,
    image_1_path: Path,
    image_2_path: Path,
    knowledge_file: Path | None = DEFAULT_KNOWLEDGE_FILE,
) -> ProbePackage:
    """Build a VLM-ready probe package for two images."""

    probe = get_probe(probe_key)
    if not image_1_path.exists():
        raise ProbeError(f"Image 1 does not exist: {image_1_path}")
    if not image_2_path.exists():
        raise ProbeError(f"Image 2 does not exist: {image_2_path}")

    plant_knowledge = load_plant_knowledge(knowledge_file)
    return ProbePackage(
        probe_id=probe.probe_id,
        species=probe.species,
        crop=probe.crop,
        image_1_path=str(image_1_path),
        image_2_path=str(image_2_path),
        prompt=build_probe_prompt(probe, plant_knowledge),
        expected_output=EXPECTED_OUTPUT,
    )


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for two-image probe package generation."""

    parser = argparse.ArgumentParser(description="Build a VLM-ready two-image observation package.")
    parser.add_argument("--probe", default=TWO_IMAGE_OBSERVATION_PROBE.key, choices=sorted(PROBES))
    parser.add_argument("--image-1", type=Path, required=True)
    parser.add_argument("--image-2", type=Path, required=True)
    parser.add_argument("--knowledge-file", type=Path, default=DEFAULT_KNOWLEDGE_FILE)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m assessment.probes_2`."""

    args = parse_args()

    try:
        package = build_probe_package(
            args.probe,
            args.image_1,
            args.image_2,
            args.knowledge_file,
        )
    except ProbeError as error:
        print(f"Probe error: {error}")
        return 1

    print(json.dumps(asdict(package), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
