"""Parser and database seeder for sample botanical knowledge references."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_KNOWLEDGE_DIR = PROJECT_ROOT / "sample" / "knowldge"

# Map filename stem to canonical and alternative species codes
SPECIES_CODE_ALIASES: dict[str, list[str]] = {
    "monstera": ["monstera", "monstera_deliciosa"],
    "peace_lily": ["spath", "peace_lily", "spathiphyllum"],
    "calathea": ["calathea", "goeppertia"],
    "snake_plant": ["snake_plant", "dracaena_trifasciata", "sansevieria"],
    "fiddle_leaf_fig": ["fiddle_leaf_fig", "ficus_lyrata"],
    "money_tree": ["money_tree", "pachira_aquatica"],
    "pothos": ["pothos", "epipremnum_aureum"],
    "spider_plant": ["spider_plant", "chlorophytum_comosum"],
    "aloe_vera": ["aloe_vera", "aloe_barbadensis_miller"],
    "zz_plant": ["zz_plant", "zamioculcas_zamiifolia"],
}


@dataclass
class ParsedProblem:
    title: str
    slug: str
    care_need: str
    visible_signs: str = ""
    healthy_contrast: str = ""
    not_this: str = ""
    likely_cause: str = ""
    action_instruction: str = ""
    urgency: str = "this_week"
    typical_hours: int = 168
    max_hours: int = 336


@dataclass
class ParsedSpeciesKnowledge:
    stem: str
    common_name: str
    scientific_name: str
    primary_code: str
    aliases: list[str]
    raw_markdown: str
    problems: list[ParsedProblem] = field(default_factory=list)


def parse_urgency_hours(urgency_str: str, recovery_text: str) -> tuple[str, int, int]:
    """Map urgency string and recovery text to (db_urgency, typical_hours, max_hours)."""
    u_norm = urgency_str.strip().lower()
    if "today" in u_norm:
        urgency = "today"
        typical, max_h = 24, 72
    elif "month" in u_norm:
        urgency = "this_month"
        typical, max_h = 672, 1344
    else:
        urgency = "this_week"
        typical, max_h = 168, 336

    # Attempt to extract precise hours / weeks from recovery text
    h_match = re.search(r"within\s+(\d+)\s+hours?,\s+at\s+most\s+(\d+)\s+hours?", recovery_text, re.I)
    if h_match:
        typical, max_h = int(h_match.group(1)), int(h_match.group(2))
    else:
        w_match = re.search(r"within\s+(\d+)\s+weeks?,\s+at\s+most\s+(\d+)\s+weeks?", recovery_text, re.I)
        if w_match:
            typical, max_h = int(w_match.group(1)) * 168, int(w_match.group(2)) * 168

    return urgency, typical, max_h


def parse_knowledge_markdown(file_path: Path) -> ParsedSpeciesKnowledge:
    """Parse one visual care reference markdown file into structured knowledge."""
    content = file_path.read_text(encoding="utf-8")
    stem = file_path.stem

    # 1. Parse header: # Common Name (Scientific Name) — visual care reference
    title_match = re.search(r"^#\s+(.*?)\s*\((.*?)\)", content, re.MULTILINE)
    if title_match:
        common_name = title_match.group(1).strip()
        scientific_name = title_match.group(2).strip()
    else:
        common_name = stem.replace("_", " ").title()
        scientific_name = stem

    aliases = SPECIES_CODE_ALIASES.get(stem, [stem])
    primary_code = aliases[0]

    # 2. Parse problems sections: ### Problem Title
    problem_blocks = re.split(r"(?m)^###\s+", content)
    problems: list[ParsedProblem] = []

    for block in problem_blocks[1:]:  # skip preamble
        lines = block.splitlines()
        if not lines:
            continue
        p_title = lines[0].strip()

        care_need = "other"
        visible_signs = ""
        healthy_contrast = ""
        not_this = ""
        likely_cause = ""
        action_instr = ""
        urgency_raw = "this week"
        recovery_raw = ""

        care_match = re.search(r"\*\s+Care need:\s*(.*)", block, re.I)
        if care_match:
            care_need = care_match.group(1).strip()

        vis_match = re.search(r"\*\s+Visible signs:\s*(.*)", block, re.I)
        if vis_match:
            visible_signs = vis_match.group(1).strip()

        contrast_match = re.search(r"\*\s+Healthy contrast:\s*(.*)", block, re.I)
        if contrast_match:
            healthy_contrast = contrast_match.group(1).strip()

        not_this_match = re.search(r"\*\s+Not to be confused with:\s*(.*)", block, re.I)
        if not_this_match:
            not_this = not_this_match.group(1).strip()

        cause_match = re.search(r"\*\s+Likely cause:\s*(.*)", block, re.I)
        if cause_match:
            likely_cause = cause_match.group(1).strip()

        act_match = re.search(r"\*\s+Action:\s*(.*)", block, re.I)
        if act_match:
            action_instr = act_match.group(1).strip()

        urg_match = re.search(r"\*\s+Urgency:\s*(.*)", block, re.I)
        if urg_match:
            urgency_raw = urg_match.group(1).strip()

        rec_match = re.search(r"\*\s+Expected recovery:\s*(.*)", block, re.I)
        if rec_match:
            recovery_raw = rec_match.group(1).strip()

        urgency, typical_h, max_h = parse_urgency_hours(urgency_raw, recovery_raw)
        slug = f"{care_need}.{re.sub(r'[^a-z0-9_]', '', p_title.lower().replace(' ', '_'))[:24]}"

        problems.append(
            ParsedProblem(
                title=p_title,
                slug=slug,
                care_need=care_need,
                visible_signs=visible_signs,
                healthy_contrast=healthy_contrast,
                not_this=not_this,
                likely_cause=likely_cause,
                action_instruction=action_instr,
                urgency=urgency,
                typical_hours=typical_h,
                max_hours=max_h,
            )
        )

    return ParsedSpeciesKnowledge(
        stem=stem,
        common_name=common_name,
        scientific_name=scientific_name,
        primary_code=primary_code,
        aliases=aliases,
        raw_markdown=content,
        problems=problems,
    )


def load_all_sample_knowledge(knowledge_dir: Path | None = None) -> list[ParsedSpeciesKnowledge]:
    """Load and parse all species knowledge documents from sample/knowldge/."""
    if knowledge_dir is None:
        knowledge_dir = SAMPLE_KNOWLEDGE_DIR

    results: list[ParsedSpeciesKnowledge] = []
    if not knowledge_dir.exists():
        return results

    for file_path in sorted(knowledge_dir.glob("*.md")):
        results.append(parse_knowledge_markdown(file_path))
    return results


def _hash_content(text: str) -> str:
    """Hash document content. Uses knowledge.hashing if available, falls back to SHA-256."""
    try:
        from knowledge.hashing import hash_document
        return hash_document(text)
    except ImportError:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seed_sample_knowledge(session: Session, knowledge_dir: Path | None = None) -> int:
    """
    Seed database with all species, active research documents, approved probe sets,
    probes, and probe actions parsed from sample/knowldge/.

    Returns the total number of seeded probe actions.

    Note: This function requires the full application dependencies (SQLAlchemy, knowledge models).
    It performs lazy imports to avoid triggering the app bootstrap at module load time.
    """
    # Lazy imports — only needed when actually seeding the database
    from sqlalchemy.orm import Session as _Session  # noqa: F811

    from knowledge.models import Probe, ProbeAction, ProbeSet, ResearchDocument, Species

    species_list = load_all_sample_knowledge(knowledge_dir)
    total_actions = 0
    now = datetime.now(UTC)

    for item in species_list:
        content_hash = _hash_content(item.raw_markdown)

        # 1. Seed species for primary code and all aliases
        for code in item.aliases:
            existing_sp = session.query(Species).filter_by(species_code=code).first()
            if not existing_sp:
                sp = Species(
                    species_code=code,
                    scientific_name=item.scientific_name,
                    common_name=item.common_name,
                )
                session.add(sp)
                session.flush()

            # 2. Seed active ResearchDocument
            existing_doc = (
                session.query(ResearchDocument)
                .filter_by(species_code=code, status="active")
                .first()
            )
            doc_id = uuid.uuid4()
            if not existing_doc:
                doc = ResearchDocument(
                    id=doc_id,
                    species_code=code,
                    title=f"{item.common_name} visual care reference",
                    body=item.raw_markdown,
                    content_hash=content_hash,
                    author="sample/knowldge",
                    status="active",
                    created_at=now,
                )
                session.add(doc)
                session.flush()
            else:
                doc_id = existing_doc.id

            # 3. Seed approved ProbeSet
            existing_set = (
                session.query(ProbeSet)
                .filter_by(species_code=code, status="approved")
                .first()
            )
            if not existing_set:
                probe_set_id = uuid.uuid4()
                ps = ProbeSet(
                    id=probe_set_id,
                    research_document_id=doc_id,
                    species_code=code,
                    source_content_hash=content_hash,
                    llm_model="sample_knowledge",
                    prompt_version="1.0.0",
                    status="approved",
                    generated_at=now,
                    approved_by="evaluation_loader",
                    approved_at=now,
                )
                session.add(ps)
                session.flush()

                # 4. Seed Probes and ProbeActions
                for priority, prob in enumerate(item.problems, start=1):
                    probe_id = uuid.uuid4()
                    p = Probe(
                        id=probe_id,
                        probe_set_id=probe_set_id,
                        slug=prob.slug,
                        care_need=prob.care_need,
                        priority=priority,
                        is_screening=(priority == 1),
                        question=f"Does the {item.common_name} show signs of {prob.title.lower()}?",
                        worse_looks_like=prob.visible_signs or prob.title,
                        better_looks_like=prob.healthy_contrast or "Healthy plant appearance.",
                        not_this=prob.not_this or "Natural plant growth variation.",
                        evidence_quote=prob.visible_signs,
                    )
                    session.add(p)
                    session.flush()

                    if prob.action_instruction:
                        action_id = uuid.uuid4()
                        act = ProbeAction(
                            id=action_id,
                            probe_id=probe_id,
                            ordering=1,
                            instruction=prob.action_instruction,
                            urgency=prob.urgency,
                            expect_typical_hours=prob.typical_hours,
                            expect_max_hours=prob.max_hours,
                            expected_signal="recovery_observed",
                        )
                        session.add(act)
                        total_actions += 1

    session.commit()
    return total_actions
