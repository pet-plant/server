"""VLM structured JSON classification metrics.

Provides precision, recall, F1, accuracy, and aggregate averaging calculations
for botanical visual assessment symptoms, probe questions, and batch photo evaluations.
"""

from __future__ import annotations

from typing import Any, Sequence


def calculate_classification_metrics(
    tp: int,
    fp: int,
    fn: int,
    tn: int,
) -> dict[str, float]:
    """Compute standard classification metrics from confusion matrix components.

    Formulas:
        Precision = TP / (TP + FP)  (0.0 if TP + FP == 0)
        Recall    = TP / (TP + FN)  (0.0 if TP + FN == 0)
        F1        = 2 * (Precision * Recall) / (Precision + Recall) (0.0 if P + R == 0)
        Accuracy  = (TP + TN) / (TP + TN + FP + FN) (1.0 if total == 0)
    """
    total = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) > 0 else (1.0 if fn == 0 else 0.0)
    recall = tp / (tp + fn) if (tp + fn) > 0 else (1.0 if fp == 0 else 0.0)
    f1 = (
        2.0 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    accuracy = (tp + tn) / total if total > 0 else 1.0

    return {
        "tp": float(tp),
        "fp": float(fp),
        "fn": float(fn),
        "tn": float(tn),
        "precision": round(precision * 100.0, 2),
        "recall": round(recall * 100.0, 2),
        "f1": round(f1 * 100.0, 2),
        "accuracy": round(accuracy * 100.0, 2),
    }


def evaluate_symptoms_classification(
    expected_symptoms: Sequence[str | dict[str, Any]],
    actual_symptoms: Sequence[str | dict[str, Any]],
    known_universe: Sequence[str] | None = None,
) -> dict[str, float]:
    """Calculate classification metrics comparing expected vs actual detected symptoms.

    Symptoms can be strings (e.g. "leaf_yellowing") or dictionaries with a "type" or "slug".
    """
    def _extract_key(item: str | dict[str, Any]) -> str:
        if isinstance(item, str):
            return item.strip().lower()
        if isinstance(item, dict):
            return str(item.get("type") or item.get("slug") or item.get("name") or "").strip().lower()
        return str(item).strip().lower()

    exp_set = {_extract_key(x) for x in expected_symptoms if _extract_key(x)}
    act_set = {_extract_key(x) for x in actual_symptoms if _extract_key(x)}

    tp = len(exp_set & act_set)
    fp = len(act_set - exp_set)
    fn = len(exp_set - act_set)

    if known_universe:
        all_symptoms = {_extract_key(s) for s in known_universe}
        tn = len(all_symptoms - (exp_set | act_set))
    else:
        # If no universe defined, TN is 0 or 1 depending on whether both are empty
        tn = 1 if (not exp_set and not act_set) else 0

    return calculate_classification_metrics(tp, fp, fn, tn)


def evaluate_probe_findings(
    expected_probes: Sequence[dict[str, Any]],
    actual_probes: Sequence[dict[str, Any]],
) -> dict[str, float]:
    """Calculate classification metrics comparing hypothesis probe answers (yes/no).

    Each probe finding is expected to have 'slug' and 'answer' ('yes'/'no').
    """
    exp_map = {
        str(p.get("slug") or p.get("id") or ""): str(p.get("answer", "")).strip().lower()
        for p in expected_probes
    }
    act_map = {
        str(p.get("slug") or p.get("id") or ""): str(p.get("answer", "")).strip().lower()
        for p in actual_probes
    }

    all_slugs = set(exp_map.keys()) | set(act_map.keys())
    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for slug in all_slugs:
        exp_ans = exp_map.get(slug, "no") == "yes"
        act_ans = act_map.get(slug, "no") == "yes"

        if exp_ans and act_ans:
            tp += 1
        elif not exp_ans and act_ans:
            fp += 1
        elif exp_ans and not act_ans:
            fn += 1
        else:
            tn += 1

    return calculate_classification_metrics(tp, fp, fn, tn)


def aggregate_batch_photo_metrics(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate per-photo evaluation results and calculate averages across all photos.

    Computes:
    - total_photos
    - successful_photos
    - failed_photos
    - success_rate_pct
    - avg_f1_score
    - avg_precision
    - avg_recall
    - avg_accuracy
    """
    total = len(results)
    if total == 0:
        return {
            "total_photos": 0,
            "successful_photos": 0,
            "failed_photos": 0,
            "success_rate_pct": 0.0,
            "avg_f1_score": 0.0,
            "avg_precision": 0.0,
            "avg_recall": 0.0,
            "avg_accuracy": 0.0,
        }

    successful = sum(1 for r in results if r.get("passed", False))
    failed = total - successful
    success_rate = (successful / total) * 100.0

    f1s = [r.get("f1_score", 0.0) for r in results if "f1_score" in r]
    precisions = [r.get("precision", 0.0) for r in results if "precision" in r]
    recalls = [r.get("recall", 0.0) for r in results if "recall" in r]
    accuracies = [r.get("accuracy", 0.0) for r in results if "accuracy" in r]

    return {
        "total_photos": total,
        "successful_photos": successful,
        "failed_photos": failed,
        "success_rate_pct": round(success_rate, 2),
        "avg_f1_score": round(sum(f1s) / len(f1s), 2) if f1s else 0.0,
        "avg_precision": round(sum(precisions) / len(precisions), 2) if precisions else 0.0,
        "avg_recall": round(sum(recalls) / len(recalls), 2) if recalls else 0.0,
        "avg_accuracy": round(sum(accuracies) / len(accuracies), 2) if accuracies else 0.0,
    }


def normalize_health_status(status_str: Any) -> str:
    """Normalize health status strings to either 'healthy' or 'unhealthy'."""
    val = str(status_str or "").strip().lower()
    if val in ("healthy", "good", "normal", "fine"):
        return "healthy"
    return "unhealthy"


def evaluate_final_dataset_metrics(
    eval_samples: Sequence[Any],
    predictions: Sequence[dict[str, Any]],
    species_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate comprehensive classification metrics on the final houseplant evaluation dataset.

    Args:
        eval_samples: Ground truth samples from eval.jsonl (or dicts).
        predictions: Model predictions with 'id' (or matching index), 'predicted_health_status', 'predicted_symptoms'.
        species_meta: Optional dictionary mapping species codes to metadata (with allowed symptom tags).

    Returns:
        Structured dictionary containing:
        - total_samples: int
        - evaluated_samples: int
        - health_status: {accuracy, precision, recall, f1, tp, fp, fn, tn}
        - symptoms_overall: {micro_precision, micro_recall, micro_f1, macro_precision, macro_recall, macro_f1}
        - by_species: dict mapping species_code to individual species metrics
        - by_symptom: dict mapping symptom_tag to precision, recall, f1, support
    """
    pred_map: dict[str, dict[str, Any]] = {}
    for p in predictions:
        p_id = str(p.get("id") or "")
        if p_id:
            pred_map[p_id] = p

    status_tp = 0
    status_fp = 0
    status_fn = 0
    status_tn = 0

    # For multi-label symptoms micro-averaging across all samples
    sym_total_tp = 0
    sym_total_fp = 0
    sym_total_fn = 0

    # Per-symptom counters for macro-averaging
    all_symptom_tags: set[str] = set()
    symptom_tps: dict[str, int] = {}
    symptom_fps: dict[str, int] = {}
    symptom_fns: dict[str, int] = {}

    def _get_val(obj: Any, key: str, default: Any = None) -> Any:
        if hasattr(obj, key):
            v = getattr(obj, key)
            return v if v is not None else default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default

    # Per-species buckets
    species_samples: dict[str, list[tuple[Any, dict[str, Any]]]] = {}

    evaluated_count = 0
    for sample in eval_samples:
        s_id = str(_get_val(sample, "id", ""))
        pred = pred_map.get(s_id)
        if not pred:
            continue

        evaluated_count += 1
        species_code = str(_get_val(sample, "species", "unknown"))
        species_samples.setdefault(species_code, []).append((sample, pred))

        # 1. Health Status Binary Metrics (Positive = 'unhealthy')
        exp_status = normalize_health_status(_get_val(sample, "status", "healthy"))
        act_status = normalize_health_status(pred.get("predicted_health_status") or pred.get("health_status", "healthy"))

        if exp_status == "unhealthy" and act_status == "unhealthy":
            status_tp += 1
        elif exp_status == "healthy" and act_status == "unhealthy":
            status_fp += 1
        elif exp_status == "unhealthy" and act_status == "healthy":
            status_fn += 1
        else:
            status_tn += 1

        # 2. Symptoms Multi-Label
        raw_exp_syms = _get_val(sample, "symptoms", []) or []
        raw_act_syms = pred.get("predicted_symptoms") or pred.get("symptoms", []) or []

        exp_sym_set = {str(s).strip().lower() for s in raw_exp_syms if str(s).strip()}
        act_sym_set = {str(s).strip().lower() for s in raw_act_syms if str(s).strip()}

        all_symptom_tags.update(exp_sym_set)
        all_symptom_tags.update(act_sym_set)

        # Micro counts
        cur_tp = len(exp_sym_set & act_sym_set)
        cur_fp = len(act_sym_set - exp_sym_set)
        cur_fn = len(exp_sym_set - act_sym_set)

        sym_total_tp += cur_tp
        sym_total_fp += cur_fp
        sym_total_fn += cur_fn

        # Per-tag counts
        for tag in exp_sym_set | act_sym_set:
            if tag in exp_sym_set and tag in act_sym_set:
                symptom_tps[tag] = symptom_tps.get(tag, 0) + 1
            elif tag not in exp_sym_set and tag in act_sym_set:
                symptom_fps[tag] = symptom_fps.get(tag, 0) + 1
            elif tag in exp_sym_set and tag not in act_sym_set:
                symptom_fns[tag] = symptom_fns.get(tag, 0) + 1

    # Aggregate Overall Health Status
    status_metrics = calculate_classification_metrics(status_tp, status_fp, status_fn, status_tn)

    # Micro Symptoms Metrics
    micro_p = sym_total_tp / (sym_total_tp + sym_total_fp) if (sym_total_tp + sym_total_fp) > 0 else 1.0
    micro_r = sym_total_tp / (sym_total_tp + sym_total_fn) if (sym_total_tp + sym_total_fn) > 0 else 1.0
    micro_f1 = (2.0 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) > 0 else 0.0

    # Macro Symptoms Metrics & Per-tag breakdown
    by_symptom: dict[str, dict[str, Any]] = {}
    macro_ps: list[float] = []
    macro_rs: list[float] = []
    macro_f1s: list[float] = []

    for tag in sorted(all_symptom_tags):
        t_tp = symptom_tps.get(tag, 0)
        t_fp = symptom_fps.get(tag, 0)
        t_fn = symptom_fns.get(tag, 0)
        tag_metrics = calculate_classification_metrics(t_tp, t_fp, t_fn, 0)

        by_symptom[tag] = {
            "tp": t_tp,
            "fp": t_fp,
            "fn": t_fn,
            "precision": tag_metrics["precision"],
            "recall": tag_metrics["recall"],
            "f1": tag_metrics["f1"],
            "support": t_tp + t_fn,
        }
        macro_ps.append(tag_metrics["precision"])
        macro_rs.append(tag_metrics["recall"])
        macro_f1s.append(tag_metrics["f1"])

    macro_p = round(sum(macro_ps) / len(macro_ps), 2) if macro_ps else (100.0 if sym_total_fp == 0 else 0.0)
    macro_r = round(sum(macro_rs) / len(macro_rs), 2) if macro_rs else (100.0 if sym_total_fp == 0 else 0.0)
    macro_f1 = round(sum(macro_f1s) / len(macro_f1s), 2) if macro_f1s else (100.0 if sym_total_fp == 0 else 0.0)

    # Per-Species Breakdown
    by_species: dict[str, dict[str, Any]] = {}
    for spec_key, pairs in sorted(species_samples.items()):
        spec_total = len(pairs)
        s_tp = s_fp = s_fn = s_tn = 0
        s_sym_tp = s_sym_fp = s_sym_fn = 0

        for s_sample, s_pred in pairs:
            e_stat = normalize_health_status(_get_val(s_sample, "status", "healthy"))
            a_stat = normalize_health_status(s_pred.get("predicted_health_status") or s_pred.get("health_status", "healthy"))
            if e_stat == "unhealthy" and a_stat == "unhealthy":
                s_tp += 1
            elif e_stat == "healthy" and a_stat == "unhealthy":
                s_fp += 1
            elif e_stat == "unhealthy" and a_stat == "healthy":
                s_fn += 1
            else:
                s_tn += 1

            r_e_syms = {str(x).strip().lower() for x in (_get_val(s_sample, "symptoms", []) or []) if str(x).strip()}
            r_a_syms = {str(x).strip().lower() for x in (s_pred.get("predicted_symptoms") or s_pred.get("symptoms", []) or []) if str(x).strip()}

            s_sym_tp += len(r_e_syms & r_a_syms)
            s_sym_fp += len(r_a_syms - r_e_syms)
            s_sym_fn += len(r_e_syms - r_a_syms)

        spec_stat_metrics = calculate_classification_metrics(s_tp, s_fp, s_fn, s_tn)
        sp_p = s_sym_tp / (s_sym_tp + s_sym_fp) if (s_sym_tp + s_sym_fp) > 0 else 1.0
        sp_r = s_sym_tp / (s_sym_tp + s_sym_fn) if (s_sym_tp + s_sym_fn) > 0 else 1.0
        sp_f1 = (2.0 * sp_p * sp_r / (sp_p + sp_r)) if (sp_p + sp_r) > 0 else 0.0

        by_species[spec_key] = {
            "total_samples": spec_total,
            "health_status": {
                "accuracy": spec_stat_metrics["accuracy"],
                "f1": spec_stat_metrics["f1"],
                "precision": spec_stat_metrics["precision"],
                "recall": spec_stat_metrics["recall"],
                "tp": s_tp,
                "fp": s_fp,
                "fn": s_fn,
                "tn": s_tn,
            },
            "symptoms": {
                "micro_f1": round(sp_f1 * 100.0, 2),
                "precision": round(sp_p * 100.0, 2),
                "recall": round(sp_r * 100.0, 2),
            },
        }

    return {
        "total_samples": len(eval_samples),
        "evaluated_samples": evaluated_count,
        "health_status": {
            "accuracy": status_metrics["accuracy"],
            "f1": status_metrics["f1"],
            "precision": status_metrics["precision"],
            "recall": status_metrics["recall"],
            "tp": status_tp,
            "fp": status_fp,
            "fn": status_fn,
            "tn": status_tn,
        },
        "symptoms": {
            "micro_f1": round(micro_f1 * 100.0, 2),
            "micro_precision": round(micro_p * 100.0, 2),
            "micro_recall": round(micro_r * 100.0, 2),
            "macro_f1": macro_f1,
            "macro_precision": macro_p,
            "macro_recall": macro_r,
        },
        "by_species": by_species,
        "by_symptom": by_symptom,
    }


