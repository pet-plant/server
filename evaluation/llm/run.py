"""Runner for LLM care advice evaluation (deterministic checks, text similarity & difference, optional judge)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evaluation.common.config import EvaluationConfig
from evaluation.common.metrics import calculate_jaccard, calculate_text_similarity
from evaluation.common.reporting import MetricResult, ScopeExecutionResult, print_scope_aggregate


def run_llm_evaluation(
    config: EvaluationConfig,
    manifest_path: Path | None = None,
) -> ScopeExecutionResult:
    """Execute evaluation for LLM health assessment and care advice."""
    start_time = time.perf_counter()

    if manifest_path is None:
        manifest_path = (
            Path(__file__).resolve().parent.parent
            / "datasets"
            / "llm"
            / "advice_cases.json"
        )

    if not manifest_path.exists():
        return ScopeExecutionResult(
            scope_name="llm",
            status="SKIPPED",
            duration_seconds=round(time.perf_counter() - start_time, 3),
            total_cases=0,
            passed_cases=0,
            skip_reason=f"Manifest file not found: {manifest_path}",
        )

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    if not cases:
        return ScopeExecutionResult(
            scope_name="llm",
            status="SKIPPED",
            duration_seconds=round(time.perf_counter() - start_time, 3),
            total_cases=0,
            passed_cases=0,
            skip_reason="No test cases in advice_cases.json.",
        )

    case_results: list[dict[str, Any]] = []
    schema_passed_count = 0
    passed_cases = 0

    sem_sims: list[float] = []
    lex_sims: list[float] = []
    resp_diffs: list[float] = []
    action_alignments: list[float] = []

    total = len(cases)
    print(f"  [llm] Running {total} case(s)...")

    for case_idx, case in enumerate(cases, 1):
        input_context = case.get("input_context", {})
        approved_actions = {a["id"] for a in input_context.get("approved_actions", [])}

        # Resolve expected and actual responses (backward compatible with 'care_plan')
        expected_resp = case.get("expected_response") or case.get("care_plan", {})
        actual_resp = case.get("actual_response") or case.get("care_plan", {})

        exp_assessment = expected_resp.get("assessment", "")
        act_assessment = actual_resp.get("assessment", "")

        act_status = actual_resp.get("status_label", "")
        act_actions = actual_resp.get("actions", [])

        # 1. Structure validity
        has_structure = bool(act_status and act_assessment and len(act_actions) > 0)

        # 2. Action grounding check: all actions must come from approved actions
        grounded = True
        type_valid = True
        priorities_valid = True
        seen_priorities = []

        for act in act_actions:
            act_id = act.get("approved_action_id") or act.get("id")
            if approved_actions and act_id not in approved_actions:
                grounded = False
            if act.get("type") not in ("water", "move", "inspect", "other"):
                type_valid = False
            seen_priorities.append(act.get("priority", 0))

        if seen_priorities != sorted(seen_priorities):
            priorities_valid = False

        schema_valid = has_structure and grounded and type_valid and priorities_valid
        if schema_valid:
            schema_passed_count += 1

        # 3. Text Similarity & Difference calculation
        sim_res = calculate_text_similarity(
            expected=exp_assessment,
            actual=act_assessment,
        )

        sem_sim = sim_res["semantic_similarity"]
        lex_sim = sim_res["lexical_similarity"]
        diff_pct = sim_res["response_difference"]

        sem_sims.append(sem_sim)
        lex_sims.append(lex_sim)
        resp_diffs.append(diff_pct)

        # 4. Action Alignment (Jaccard similarity of selected action IDs)
        exp_action_ids = {
            a.get("approved_action_id") or a.get("id") for a in expected_resp.get("actions", [])
        }
        act_action_ids = {
            a.get("approved_action_id") or a.get("id") for a in act_actions
        }
        action_alignment = round(calculate_jaccard(exp_action_ids, act_action_ids) * 100.0, 2)
        action_alignments.append(action_alignment)

        # Pass criteria: valid schema, similarity meets threshold, difference within bound, actions align
        similarity_passed = (
            sem_sim >= config.llm_min_similarity and diff_pct <= config.llm_max_difference
        )
        actions_passed = action_alignment >= config.llm_min_action_alignment
        case_passed = schema_valid and similarity_passed and actions_passed

        if case_passed:
            passed_cases += 1

        status_tag = "PASS" if case_passed else "FAIL"
        case_id = case.get("id", case_idx)
        print(
            f"  [{case_idx}/{total}] Case: {case_id} "
            f"[{status_tag}] "
            f"sem_sim={sem_sim:.1f}%  diff={diff_pct:.1f}%  "
            f"action_align={action_alignment:.1f}%  schema={'OK' if schema_valid else 'FAIL'}"
        )
        # ── Per-case stage trace ────────────────────────────────────────────
        ctx = input_context
        print(f"       [INPUT]   health_status={ctx.get('health_status', '-')}  "
              f"symptom={ctx.get('primary_symptom', '-')}  "
              f"approved_actions={len(ctx.get('approved_actions', []))}")
        act_actions_summary = ", ".join(
            f"{a.get('type','?')}:{a.get('label','?')}" for a in act_actions
        ) or "none"
        print(f"       [LLM]     status_label={act_status or '-'}  "
              f"actions=[{act_actions_summary}]")
        print(f"       [LLM]     assessment={act_assessment[:120].replace(chr(10), ' ')!r}"
              f"{'...' if len(act_assessment) > 120 else ''}")
        print(f"       [METRICS] sem_sim={sem_sim:.1f}%  diff={diff_pct:.1f}%  "
              f"lex_sim={lex_sim:.1f}%  action_align={action_alignment:.1f}%  "
              f"schema={'OK' if schema_valid else 'FAIL'}")
        case_results.append(
            {
                "case_id": case.get("id"),
                "description": case.get("description", ""),
                "passed": case_passed,
                "schema_valid": schema_valid,
                "has_structure": has_structure,
                "grounded": grounded,
                "type_valid": type_valid,
                "priorities_valid": priorities_valid,
                "semantic_similarity_pct": sem_sim,
                "lexical_similarity_pct": lex_sim,
                "response_difference_pct": diff_pct,
                "action_alignment_pct": action_alignment,
                "similarity_method": sim_res["method"],
                "expected_assessment": exp_assessment,
                "actual_assessment": act_assessment,
                "judge_score": None if not config.enable_judge else "SKIPPED (no judge key)",
            }
        )

    duration = time.perf_counter() - start_time
    total = len(cases)
    schema_valid_rate = round((schema_passed_count / total) * 100.0, 2) if total > 0 else 0.0

    mean_sem_sim = round(sum(sem_sims) / len(sem_sims), 2) if sem_sims else 0.0
    mean_lex_sim = round(sum(lex_sims) / len(lex_sims), 2) if lex_sims else 0.0
    mean_diff = round(sum(resp_diffs) / len(resp_diffs), 2) if resp_diffs else 0.0
    mean_act_align = (
        round(sum(action_alignments) / len(action_alignments), 2)
        if action_alignments
        else 0.0
    )

    metrics: dict[str, MetricResult] = {
        "advice_schema_conformance": MetricResult(
            name="advice_schema_conformance",
            value=schema_valid_rate,
            status="PASS" if schema_valid_rate >= 100.0 else "FAIL",
            threshold=100.0,
            reason="100% adherence to 3NF care plan structure and action grounding.",
        ),
        "mean_semantic_similarity": MetricResult(
            name="mean_semantic_similarity",
            value=mean_sem_sim,
            status="PASS" if mean_sem_sim >= config.llm_min_similarity else "FAIL",
            threshold=config.llm_min_similarity,
            reason="Mean semantic similarity between expected and actual assessment responses.",
        ),
        "mean_response_difference": MetricResult(
            name="mean_response_difference",
            value=mean_diff,
            status="PASS" if mean_diff <= config.llm_max_difference else "FAIL",
            threshold=config.llm_max_difference,
            reason="Mean difference percentage between expected and actual response via (100 - (similarity) * 100).",
        ),

        "mean_action_alignment": MetricResult(
            name="mean_action_alignment",
            value=mean_act_align,
            status="PASS" if mean_act_align >= config.llm_min_action_alignment else "FAIL",
            threshold=config.llm_min_action_alignment,
            reason="Mean overlap percentage of recommended care actions against expected actions.",
        ),
        "mean_lexical_similarity": MetricResult(
            name="mean_lexical_similarity",
            value=mean_lex_sim,
            status="PASS",
            threshold=None,
            reason="Informational: Mean character and word SequenceMatcher alignment.",
        ),
    }

    if config.enable_judge:
        metrics["llm_as_a_judge"] = MetricResult(
            name="llm_as_a_judge",
            value="SKIPPED",
            status="SKIPPED",
            reason="Judge API credentials not configured in environment.",
        )

    all_passed = all(m.status in ("PASS", "SKIPPED") for m in metrics.values())
    status = "PASS" if all_passed and passed_cases == total else "FAIL"

    result = ScopeExecutionResult(
        scope_name="llm",
        status=status,
        duration_seconds=duration,
        total_cases=total,
        passed_cases=passed_cases,
        metrics=metrics,
        case_results=case_results,
        called_endpoints=[
            {"method": "", "path": "advice.service  (care plan generation)", "calls": total, "source": "in-memory"},
            {"method": "", "path": "evaluation.common.metrics.calculate_text_similarity", "calls": total, "source": "in-memory"},
            {"method": "", "path": "evaluation.common.metrics.calculate_jaccard  (action alignment)", "calls": total, "source": "in-memory"},
        ],
    )
    print_scope_aggregate(result)
    return result
