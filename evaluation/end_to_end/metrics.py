"""Metrics calculation for end-to-end pipeline scenario evaluations."""

from __future__ import annotations

from typing import Any

from evaluation.common.metrics import calculate_percentile


def evaluate_end_to_end_metrics(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate scenario success rate, contract compliance, and latency percentiles."""
    total_scenarios = len(scenario_results)
    passed_scenarios = sum(1 for s in scenario_results if s["passed"])

    total_steps = 0
    valid_fe_envelopes = 0
    latencies_ms: list[float] = []

    for sc in scenario_results:
        pipeline_latency = sc.get("pipeline_latency_ms")
        if pipeline_latency is None:
            pipeline_latency = sc.get("duration_ms", 0.0)
        latencies_ms.append(pipeline_latency)
        for st in sc.get("steps", []):
            total_steps += 1
            if st.get("fe_valid"):
                valid_fe_envelopes += 1

    ssr = round((passed_scenarios / total_scenarios) * 100.0, 2) if total_scenarios > 0 else 0.0
    fe_rate = round((valid_fe_envelopes / total_steps) * 100.0, 2) if total_steps > 0 else 100.0

    med_lat = calculate_percentile(latencies_ms, 50.0)
    p90_lat = calculate_percentile(latencies_ms, 90.0)
    p95_lat = calculate_percentile(latencies_ms, 95.0)

    return {
        "scenario_success_rate": ssr,
        "total_scenarios": total_scenarios,
        "passed_scenarios": passed_scenarios,
        "total_steps": total_steps,
        "fe_envelope_compliance_rate": fe_rate,
        "latency_ms": {
            "median": med_lat,
            "p90": p90_lat,
            "p95": p95_lat,
        },
    }
