"""Standardized JSON, JSONL, and Markdown evaluation report generators."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


def is_latency_metric(name: str) -> bool:
    """Determine if a metric represents duration or latency in milliseconds."""
    name_lower = name.lower()
    return (
        name_lower.endswith("_ms")
        or name_lower.startswith("ms_")
        or "_ms_" in name_lower
        or "latency" in name_lower
        or "duration" in name_lower
    )


def is_percentage_metric(name: str) -> bool:
    """Determine if a metric represents a percentage or fractional rate."""
    if is_latency_metric(name):
        return False
    name_lower = name.lower()
    return any(
        kw in name_lower
        for kw in (
            "accuracy",
            "f1",
            "iou",
            "rate",
            "similarity",
            "difference",
            "conformance",
            "compliance",
            "alignment",
            "overlap",
            "precision",
            "recall",
        )
    )


def format_metric_value(name: str, value: Any) -> str:
    """Format metric value clearly, appending % or ms when applicable."""
    if not isinstance(value, (int, float)):
        return str(value)
    if is_latency_metric(name):
        return f"{value:.2f}ms"
    if is_percentage_metric(name):
        # Convert 0.0-1.0 normalized ratios (like accuracy, f1, iou) into 0-100%
        if (
            0.0 <= value <= 1.0
            and not any(
                name.endswith(s)
                for s in (
                    "_rate",
                    "_similarity",
                    "_difference",
                    "_conformance",
                    "_compliance",
                    "_alignment",
                )
            )
        ):
            return f"{value * 100.0:.2f}%"
        return f"{value:.2f}%"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def format_metric_threshold(name: str, threshold: float | None) -> str:
    """Format threshold clearly with direction and % where applicable."""
    if threshold is None:
        return "-"
    name_lower = name.lower()
    if is_latency_metric(name):
        return f"<= {threshold:.0f}ms"
    if is_percentage_metric(name):
        if (
            0.0 <= threshold <= 1.0
            and not any(
                name.endswith(s)
                for s in (
                    "_rate",
                    "_similarity",
                    "_difference",
                    "_conformance",
                    "_compliance",
                    "_alignment",
                )
            )
        ):
            thresh_pct = threshold * 100.0
        else:
            thresh_pct = threshold
        if any(kw in name_lower for kw in ("difference", "error", "false")):
            return f"<= {thresh_pct:.2f}%"
        return f">= {thresh_pct:.2f}%"
    return str(threshold)


@dataclass
class MetricResult:
    name: str
    value: float | int | str
    status: Literal["PASS", "FAIL", "SKIPPED"]
    threshold: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "formatted_value": format_metric_value(self.name, self.value),
            "status": self.status,
            "threshold": self.threshold,
            "reason": self.reason,
        }




@dataclass
class ScopeExecutionResult:
    scope_name: str
    status: Literal["PASS", "FAIL", "SKIPPED"]
    duration_seconds: float
    total_cases: int
    passed_cases: int
    metrics: dict[str, MetricResult] = field(default_factory=dict)
    case_results: list[dict[str, Any]] = field(default_factory=list)
    skip_reason: str | None = None
    # List of endpoint records: {"method": str, "path": str, "calls": int, "source": str}
    called_endpoints: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_name": self.scope_name,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 3),
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "metrics": {k: v.to_dict() for k, v in self.metrics.items()},
            "skip_reason": self.skip_reason,
            "called_endpoints": self.called_endpoints,
        }


# Numeric fields to average from case-level results, with display labels.
_CASE_AVG_FIELDS: list[tuple[str, str]] = [
    ("semantic_similarity_pct",  "Avg Semantic Similarity"),
    ("response_difference_pct",  "Avg Response Difference"),
    ("lexical_similarity_pct",   "Avg Lexical Similarity"),
    ("action_alignment_pct",     "Avg Action Alignment"),
    ("f1_score",                 "Avg F1 Score"),
    ("precision",                "Avg Precision"),
    ("recall",                   "Avg Recall"),
    ("accuracy",                 "Avg Accuracy"),
    ("confidence_delta",         "Avg Confidence Delta"),
    ("pipeline_latency_ms",      "Avg Pipeline Latency"),
    ("duration_ms",              "Avg Case Duration"),
]


def _compute_case_averages(
    case_results: list[dict],
) -> list[tuple[str, float]]:
    """Compute averages of numeric metric fields across all case results."""
    avgs: list[tuple[str, float]] = []
    for field, label in _CASE_AVG_FIELDS:
        values = [
            c[field]
            for c in case_results
            if isinstance(c.get(field), (int, float))
        ]
        if values:
            avgs.append((label, round(sum(values) / len(values), 2)))
    return avgs


def _generate_confusion_matrices(case_results: list[dict[str, Any]]) -> list[str]:
    """Generate Markdown confusion matrices for health status and probe classification."""
    lines: list[str] = []

    # 1. Health Status Multi-Class Confusion Matrix
    has_health_status = any(
        "expected_health_status" in c and "actual_health_status" in c
        for c in case_results
    )
    if has_health_status:
        all_classes_set: set[str] = set()
        for c in case_results:
            if c.get("expected_health_status"):
                all_classes_set.add(str(c["expected_health_status"]))
            if c.get("actual_health_status"):
                all_classes_set.add(str(c["actual_health_status"]))

        canonical_order = ["healthy", "possibly_unhealthy", "unhealthy"]
        classes = [cls for cls in canonical_order if cls in all_classes_set]
        classes += sorted(all_classes_set - set(classes))

        matrix: dict[str, dict[str, int]] = {
            exp: {act: 0 for act in classes}
            for exp in classes
        }
        for c in case_results:
            exp = str(c.get("expected_health_status", ""))
            act = str(c.get("actual_health_status", ""))
            if exp in matrix and act in matrix[exp]:
                matrix[exp][act] += 1

        lines.append("#### Health Status Multi-Class Confusion Matrix")
        lines.append("")
        header = "| Expected \\ Actual | " + " | ".join(f"`{cls}`" for cls in classes) + " | Total |"
        separator = "|---|" + "|".join("---" for _ in classes) + "|---|"
        lines.append(header)
        lines.append(separator)

        col_totals = {act: 0 for act in classes}
        grand_total = 0

        for exp in classes:
            row_vals = []
            row_sum = 0
            for act in classes:
                val = matrix[exp][act]
                row_sum += val
                col_totals[act] += val
                row_vals.append(str(val))
            grand_total += row_sum
            lines.append(f"| **`{exp}`** | " + " | ".join(row_vals) + f" | **{row_sum}** |")

        totals_row = "| **Total** | " + " | ".join(f"**{col_totals[act]}**" for act in classes) + f" | **{grand_total}** |"
        lines.append(totals_row)
        lines.append("")

    # 2. Binary Probe Findings Confusion Matrix
    has_probes = any(
        "expected_probe" in c and "actual_probe" in c
        for c in case_results
    )
    if has_probes:
        tp = sum(1 for c in case_results if str(c.get("expected_probe", "")).strip().lower() == "yes" and str(c.get("actual_probe", "")).strip().lower() == "yes")
        fp = sum(1 for c in case_results if str(c.get("expected_probe", "")).strip().lower() == "no" and str(c.get("actual_probe", "")).strip().lower() == "yes")
        fn = sum(1 for c in case_results if str(c.get("expected_probe", "")).strip().lower() == "yes" and str(c.get("actual_probe", "")).strip().lower() == "no")
        tn = sum(1 for c in case_results if str(c.get("expected_probe", "")).strip().lower() == "no" and str(c.get("actual_probe", "")).strip().lower() == "no")

        total_actual_pos = tp + fn
        total_actual_neg = fp + tn
        total_pred_pos = tp + fp
        total_pred_neg = fn + tn
        total_probes = total_actual_pos + total_actual_neg

        lines.append("#### Probe Findings Binary Confusion Matrix (Yes/No)")
        lines.append("")
        lines.append("| Actual \\ Predicted | Predicted Positive (Yes) | Predicted Negative (No) | Total |")
        lines.append("|---|---|---|---|")
        lines.append(f"| **Actual Positive (Yes)** | **{tp}** (TP) | **{fn}** (FN) | **{total_actual_pos}** |")
        lines.append(f"| **Actual Negative (No)** | **{fp}** (FP) | **{tn}** (TN) | **{total_actual_neg}** |")
        lines.append(f"| **Total** | **{total_pred_pos}** | **{total_pred_neg}** | **{total_probes}** |")
        lines.append("")

    return lines


def print_scope_aggregate(res: "ScopeExecutionResult") -> None:
    """Print a formatted aggregation score block for a scope to the terminal."""
    scope = res.scope_name.upper()
    n = res.total_cases
    pass_rate = round(res.passed_cases / n * 100.0, 1) if n > 0 else 0.0
    width = 62
    bar = "=" * width

    print(f"\n  {bar}")
    print(f"  AGGREGATE SCORES — {scope}")
    print(f"  {bar}")
    print(f"  {'Overall Status':<32} {res.status}")
    print(f"  {'Cases Passed':<32} {res.passed_cases}/{n}  ({pass_rate:.1f}%)")
    print(f"  {'Duration':<32} {res.duration_seconds:.3f}s")

    # ── Scope-level metrics (thresholded) ────────────────────────────
    if res.metrics:
        print(f"  {'-' * width}")
        print(f"  {'Scope Metric':<38} {'Value':>8}  {'Threshold':>10}  Status")
        print(f"  {'-' * width}")
        for m in res.metrics.values():
            val_str = format_metric_value(m.name, m.value)
            thresh_str = format_metric_threshold(m.name, m.threshold)
            icon = "✓" if m.status == "PASS" else ("~" if m.status == "SKIPPED" else "✗")
            label = m.name.replace("_", " ").title()
            print(f"  {icon} {label:<36} {val_str:>8}  {thresh_str:>10}  {m.status}")

    # ── Confusion matrices (if classification scope) ─────────────────
    if res.case_results:
        has_health_status = any(
            "expected_health_status" in c and "actual_health_status" in c
            for c in res.case_results
        )
        if has_health_status:
            all_classes_set = set()
            for c in res.case_results:
                if c.get("expected_health_status"):
                    all_classes_set.add(str(c["expected_health_status"]))
                if c.get("actual_health_status"):
                    all_classes_set.add(str(c["actual_health_status"]))
            canonical_order = ["healthy", "possibly_unhealthy", "unhealthy"]
            classes = [cls for cls in canonical_order if cls in all_classes_set]
            classes += sorted(all_classes_set - set(classes))
            matrix = {exp: {act: 0 for act in classes} for exp in classes}
            for c in res.case_results:
                exp = str(c.get("expected_health_status", ""))
                act = str(c.get("actual_health_status", ""))
                if exp in matrix and act in matrix[exp]:
                    matrix[exp][act] += 1
            print(f"  {'-' * width}")
            print("  Confusion Matrix (Health Status):")
            print(f"  {'-' * width}")
            header_str = "    Exp \\ Pred".ljust(22) + "".join(f"{cls[:11]:>12}" for cls in classes)
            print(header_str)
            for exp in classes:
                row_str = f"    {exp[:18]:<18}  " + "".join(f"{matrix[exp][act]:>12}" for act in classes)
                print(row_str)

    # ── Case-level averages (computed from raw results) ───────────────
    if res.case_results:
        case_avgs = _compute_case_averages(res.case_results)
        if case_avgs:
            print(f"  {'-' * width}")
            print(f"  Avg across {n} case(s):")
            print(f"  {'-' * width}")
            for label, avg_val in case_avgs:
                label_lower = label.lower()
                if "ms" in label_lower or "latency" in label_lower or "duration" in label_lower:
                    unit = "ms"
                elif "delta" in label_lower:
                    unit = ""
                else:
                    unit = "%"
                print(f"    {label:<34} {avg_val:>8.2f}{unit}")


    # ── Endpoints / pipeline stages called ───────────────────────
    if res.called_endpoints:
        print(f"  {'-' * width}")
        print(f"  Endpoints / Stages Called:")
        print(f"  {'-' * width}")
        for ep in res.called_endpoints:
            method = ep.get("method", "")
            path   = ep.get("path", "")
            calls  = ep.get("calls", 1)
            source = ep.get("source", "")
            calls_str = f"x{calls}" if calls > 1 else "   "
            src_str = f"  [{source}]" if source else ""
            if method:
                print(f"    {method:<8} {path:<40} {calls_str}{src_str}")
            else:
                # Internal stage / no method
                print(f"    ▸ {path:<46} {calls_str}{src_str}")

    print(f"  {bar}\n")



@dataclass
class EvaluationRunSummary:
    run_id: str
    timestamp_utc: str
    duration_seconds: float
    overall_status: Literal["PASS", "FAIL", "SKIPPED"]
    scopes: dict[str, ScopeExecutionResult] = field(default_factory=dict)
    git_commit: str = ""
    python_version: str = field(default_factory=lambda: sys.version.split()[0])
    models_used: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "duration_seconds": round(self.duration_seconds, 3),
            "overall_status": self.overall_status,
            "git_commit": self.git_commit,
            "python_version": self.python_version,
            "models_used": self.models_used,
            "scopes": {k: v.to_dict() for k, v in self.scopes.items()},
        }


def get_git_commit() -> str:
    """Safely get current short git commit hash if in a repo."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if res.returncode == 0:
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def generate_markdown_summary(summary: EvaluationRunSummary) -> str:
    """Generate a clean, readable Markdown report from the evaluation summary."""
    lines: list[str] = [
        f"# Pet-Plant Performance Evaluation Report — `{summary.run_id[:8]}`",
        "",
        f"- **Run ID:** `{summary.run_id}`",
        f"- **Timestamp:** `{summary.timestamp_utc}`",
        f"- **Duration:** `{summary.duration_seconds:.2f}s`",
        f"- **Overall Status:** **{summary.overall_status}**",
        f"- **Git Commit:** `{summary.git_commit}`",
        f"- **Python Version:** `{summary.python_version}`",
        "",
        "## Active Models & Environment",
        "",
        "| Role | Model / Setting |",
        "|---|---|",
    ]

    if summary.models_used:
        for role, name in summary.models_used.items():
            formatted_role = role.replace("_", " ").title()
            lines.append(f"| **{formatted_role}** | `{name}` |")
    else:
        lines.append("| **Evaluation Suite** | Standard baseline models |")

    lines.extend([
        "",
        "## Scope Summary Table",
        "",
        "| Scope | Status | Cases Passed | Duration | Key Metrics | Notes |",
        "|---|---|---|---|---|---|",
    ])

    for scope_name, res in summary.scopes.items():
        case_ratio = f"{res.passed_cases}/{res.total_cases}" if res.total_cases > 0 else "N/A"
        dur = f"{res.duration_seconds:.2f}s"
        metrics_summary = []
        for m_name, m_val in res.metrics.items():
            formatted_val = format_metric_value(m_name, m_val.value)
            metrics_summary.append(f"{m_name}={formatted_val}")
        metrics_str = ", ".join(metrics_summary) if metrics_summary else "-"
        notes = res.skip_reason or "-"
        lines.append(
            f"| `{scope_name}` | **{res.status}** | {case_ratio} | {dur} | {metrics_str} | {notes} |"
        )

    lines.append("")
    lines.append("## Aggregation Scorecard")
    lines.append("")
    lines.append("| Scope | Metric | Value | Threshold | Status |")
    lines.append("|---|---|---|---|---|")

    for scope_name, res in summary.scopes.items():
        if res.skip_reason or not res.metrics:
            pass_rate = 0.0
            lines.append(
                f"| `{scope_name}` | *(skipped)* | — | — | **{res.status}** |"
            )
            continue
        for idx, m in enumerate(res.metrics.values()):
            scope_col = f"`{scope_name}`" if idx == 0 else ""
            val_str = format_metric_value(m.name, m.value)
            thresh_str = format_metric_threshold(m.name, m.threshold)
            status_str = f"**{m.status}**"
            label = m.name.replace("_", " ").title()
            lines.append(f"| {scope_col} | {label} | {val_str} | {thresh_str} | {status_str} |")
        # Case pass rate row
        pass_rate = (
            round(res.passed_cases / res.total_cases * 100.0, 1)
            if res.total_cases > 0 else 0.0
        )
        lines.append(
            f"| | **Cases Passed** | {res.passed_cases}/{res.total_cases} ({pass_rate:.1f}%) | — | **{res.status}** |"
        )
        lines.append("| | | | | |")

    lines.append("")
    lines.append("## Detailed Scope Metrics")
    lines.append("")

    for scope_name, res in summary.scopes.items():
        lines.append(f"### Scope: `{scope_name}` ({res.status})")
        if res.skip_reason:
            lines.append(f"> **Skipped:** {res.skip_reason}")
            lines.append("")
            continue

        if not res.metrics:
            lines.append("No metric details recorded.")
            lines.append("")
            continue

        lines.append("| Metric | Value | Threshold | Status | Note |")
        lines.append("|---|---|---|---|---|")
        for m in res.metrics.values():
            val_str = format_metric_value(m.name, m.value)
            thresh_str = format_metric_threshold(m.name, m.threshold)
            reason_str = m.reason or "-"
            lines.append(f"| `{m.name}` | {val_str} | {thresh_str} | **{m.status}** | {reason_str} |")
        lines.append("")


        # Add Confusion Matrices for classification scopes (e.g. VLM)
        confusion_lines = _generate_confusion_matrices(res.case_results)
        if confusion_lines:
            lines.extend(confusion_lines)

        # Add Per-Case Response Comparison & Difference Table for scopes with candidate comparison
        has_text_comparison = any(
            "semantic_similarity_pct" in c or "response_difference_pct" in c
            for c in res.case_results
        )

        if has_text_comparison:
            lines.append(f"#### `{scope_name}` Response Similarity & Difference Breakdown")
            lines.append("")
            lines.append(
                "| Case ID | Expected Assessment | Actual Assessment | Similarity (%) | Difference (%) | Action Overlap (%) | Status |"
            )
            lines.append("|---|---|---|---|---|---|---|")
            for c in res.case_results:
                cid = c.get("case_id", "-")
                exp_txt = c.get("expected_assessment", "")
                act_txt = c.get("actual_assessment", "")
                # Render full expected and actual assessment, safely escaping pipes and newlines for markdown tables
                exp_display = (exp_txt or "-").replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").strip()
                act_display = (act_txt or "-").replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").strip()
                sim_pct = f"{c.get('semantic_similarity_pct', 0.0):.2f}%"
                diff_pct = f"{c.get('response_difference_pct', 0.0):.2f}%"
                act_align = (
                    f"{c.get('action_alignment_pct', 0.0):.2f}%"
                    if "action_alignment_pct" in c
                    else "-"
                )
                case_st = "**PASS**" if c.get("passed", False) else "**FAIL**"
                lines.append(
                    f"| `{cid}` | {exp_display} | {act_display} | {sim_pct} | {diff_pct} | {act_align} | {case_st} |"
                )
            lines.append("")
            lines.append("> *Note: Difference (%) is calculated using the formula `(100 - (similarity) * 100)` where similarity is normalized in [0.0, 1.0].*")
            lines.append("")

        # Endpoints / pipeline stages called
        if res.called_endpoints:
            lines.append(f"#### `{scope_name}` Endpoints / Stages Called")
            lines.append("")
            lines.append("| Method | Path / Stage | Calls | Source |")
            lines.append("|---|---|---|---|")
            for ep in res.called_endpoints:
                method = ep.get("method") or "—"
                path = ep.get("path", "")
                calls = ep.get("calls", 1)
                source = ep.get("source", "")
                lines.append(f"| `{method}` | `{path}` | {calls} | {source} |")
            lines.append("")
    return "\n".join(lines)




def write_run_report(
    summary: EvaluationRunSummary,
    reports_base_dir: Path,
    keep_latest: bool = True,
    run_log: str | None = None,
) -> Path:
    """
    Write summary.json, summary.md, per-scope JSONL files, and an optional run.log.
    Optionally mirrors latest report into reports_base_dir / 'latest'.
    """
    run_dir = reports_base_dir / summary.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write summary.json
    summary_json_path = run_dir / "summary.json"
    with open(summary_json_path, "w", encoding="utf-8") as f:
        json.dump(summary.to_dict(), f, indent=2)

    # 2. Write summary.md
    summary_md_path = run_dir / "summary.md"
    with open(summary_md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown_summary(summary))

    # 3. Write per-scope JSONL files
    for scope_name, res in summary.scopes.items():
        if res.case_results:
            jsonl_path = run_dir / f"{scope_name}.jsonl"
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for case in res.case_results:
                    f.write(json.dumps(case) + "\n")

    # 4. Write run.log — full captured stdout for this run
    log_path: Path | None = None
    if run_log is not None:
        log_path = run_dir / "run.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(run_log)

    # 5. Mirror to 'latest/'
    if keep_latest:
        latest_dir = reports_base_dir / "latest"
        latest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(summary_json_path, latest_dir / "summary.json")
        shutil.copy2(summary_md_path, latest_dir / "summary.md")
        for scope_name, res in summary.scopes.items():
            if res.case_results:
                src_jsonl = run_dir / f"{scope_name}.jsonl"
                shutil.copy2(src_jsonl, latest_dir / f"{scope_name}.jsonl")
        if log_path is not None:
            shutil.copy2(log_path, latest_dir / "run.log")

    return run_dir
