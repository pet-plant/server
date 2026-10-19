"""Dataset loader and metadata schemas for the final houseplant condition evaluation dataset.

Loads:
- `eval.jsonl`: 505 human-reviewed houseplant images labeled healthy/unhealthy with symptoms.
- `species.json`: Botanical knowledge and allowed symptom universes per species.
- `images/`: Local image files matching dataset rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

DATASET_FINAL_DIR = Path(__file__).resolve().parent.parent / "datasets" / "final"


@dataclass(frozen=True)
class SpeciesMetadata:
    """Botanical knowledge and symptom constraints for one species."""

    key: str
    name: str
    knowledge: str
    allowed_symptoms: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinalDatasetSample:
    """One human-annotated sample from eval.jsonl."""

    id: str
    species: str
    image_rel_path: str
    status: str
    symptoms: tuple[str, ...]
    note: str = ""
    reviewed: bool = True
    source: str = ""
    post_id: str | None = None
    permalink: str | None = None
    image_url: str | None = None
    sha256: str | None = None
    resolved_image_path: Path | None = None


@dataclass
class FinalDataset:
    """Container for the 505-sample houseplant condition benchmark dataset."""

    dataset_dir: Path
    samples: list[FinalDatasetSample] = field(default_factory=list)
    species_meta: dict[str, SpeciesMetadata] = field(default_factory=dict)
    symptom_descriptions: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.samples)

    def __iter__(self):
        return iter(self.samples)

    def __getitem__(self, index: int) -> FinalDatasetSample:
        return self.samples[index]

    def filter_by_species(self, species_key: str) -> list[FinalDatasetSample]:
        """Return all samples matching a given species code."""
        return [s for s in self.samples if s.species == species_key]

    @property
    def species_counts(self) -> dict[str, int]:
        """Count of samples per species."""
        counts: dict[str, int] = {}
        for s in self.samples:
            counts[s.species] = counts.get(s.species, 0) + 1
        return counts

    @property
    def status_counts(self) -> dict[str, int]:
        """Count of healthy vs unhealthy samples."""
        counts: dict[str, int] = {}
        for s in self.samples:
            counts[s.status] = counts.get(s.status, 0) + 1
        return counts


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_KNOWLEDGE_DIR = PROJECT_ROOT / "sample" / "knowldge"


def extract_approved_sample_knowledge(species_key: str) -> str:
    """Load approved visual care reference from sample/knowldge/<species_key>.md if present."""
    import re

    md_path = SAMPLE_KNOWLEDGE_DIR / f"{species_key}.md"
    if not md_path.is_file():
        # Check alias (e.g., monstera_deliciosa -> monstera.md)
        alias_key = species_key.split("_")[0]
        md_path = SAMPLE_KNOWLEDGE_DIR / f"{alias_key}.md"
        if not md_path.is_file():
            return ""

    content = md_path.read_text(encoding="utf-8")
    healthy_match = re.search(r"## Healthy appearance\s*\n\n(.*?)(?=\n\n## Problems|\Z)", content, re.DOTALL)
    healthy_text = healthy_match.group(1).strip() if healthy_match else ""

    problems_match = re.split(r"(?m)^###\s+", content)
    problem_summaries = []
    for block in problems_match[1:]:
        lines = block.splitlines()
        title = lines[0].strip()
        vis = re.search(r"\*\s+Visible signs:\s*(.*)", block, re.I)
        not_this = re.search(r"\*\s+Not to be confused with:\s*(.*)", block, re.I)
        vis_text = vis.group(1).strip() if vis else ""
        not_text = not_this.group(1).strip() if not_this else ""
        desc = f"- {title}: {vis_text}"
        if not_text:
            desc += f" (Caution: {not_text})"
        problem_summaries.append(desc)

    parts = []
    if healthy_text:
        parts.append(f"Healthy Appearance Baseline:\n{healthy_text}")
    if problem_summaries:
        parts.append("Approved Visual Symptoms & Diagnostic Cues:\n" + "\n".join(problem_summaries))
    return "\n\n".join(parts)


def load_final_dataset(
    dataset_dir: Path | str | None = None,
    verify_images: bool = True,
) -> FinalDataset:
    """Load and validate the final houseplant condition evaluation dataset.

    Args:
        dataset_dir: Root directory of the dataset (defaults to `evaluation/datasets/final`).
        verify_images: When True, checks that each referenced image exists and is non-empty.

    Returns:
        A validated `FinalDataset` instance.
    """
    root = Path(dataset_dir) if dataset_dir else DATASET_FINAL_DIR
    eval_file = root / "eval.jsonl"
    species_file = root / "species.json"

    if not eval_file.is_file():
        raise FileNotFoundError(f"Final dataset labels not found at {eval_file}")
    if not species_file.is_file():
        raise FileNotFoundError(f"Final dataset species metadata not found at {species_file}")

    # 1. Parse species.json and enrich with approved knowledge from sample/knowldge/
    with open(species_file, encoding="utf-8") as f:
        meta_raw = json.load(f)

    species_dict: dict[str, SpeciesMetadata] = {}
    for s_key, s_val in meta_raw.get("species", {}).items():
        approved_kb = extract_approved_sample_knowledge(s_key)
        knowledge = approved_kb if approved_kb else s_val.get("knowledge", "")
        species_dict[s_key] = SpeciesMetadata(
            key=s_key,
            name=s_val.get("name", s_key),
            knowledge=knowledge,
            allowed_symptoms=tuple(s_val.get("symptoms", [])),
        )

    symptom_descriptions: dict[str, str] = meta_raw.get("symptoms", {})

    # 2. Parse eval.jsonl
    samples: list[FinalDatasetSample] = []
    with open(eval_file, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)

            sample_id = row.get("id") or f"sample_{line_num}"
            species = row.get("species", "")
            img_rel = row.get("image", "")
            status = str(row.get("status", "healthy")).strip().lower()
            symptoms = tuple(row.get("symptoms") or [])

            resolved_path = (root / img_rel).resolve()
            if verify_images and (not resolved_path.is_file() or resolved_path.stat().st_size < 100):
                resolved_path = None

            samples.append(
                FinalDatasetSample(
                    id=sample_id,
                    species=species,
                    image_rel_path=img_rel,
                    status=status,
                    symptoms=symptoms,
                    note=row.get("note", ""),
                    reviewed=bool(row.get("reviewed", False)),
                    source=row.get("source", ""),
                    post_id=row.get("post_id"),
                    permalink=row.get("permalink"),
                    image_url=row.get("image_url"),
                    sha256=row.get("sha256"),
                    resolved_image_path=resolved_path,
                )
            )

    return FinalDataset(
        dataset_dir=root,
        samples=samples,
        species_meta=species_dict,
        symptom_descriptions=symptom_descriptions,
    )
