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
    - avg_semantic_similarity_pct
    - avg_response_difference_pct
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
            "avg_semantic_similarity_pct": 0.0,
            "avg_response_difference_pct": 0.0,
            "avg_f1_score": 0.0,
            "avg_precision": 0.0,
            "avg_recall": 0.0,
            "avg_accuracy": 0.0,
        }

    successful = sum(1 for r in results if r.get("passed", False))
    failed = total - successful
    success_rate = (successful / total) * 100.0

    sem_sims = [r.get("semantic_similarity_pct", 0.0) for r in results if "semantic_similarity_pct" in r]
    diff_pcts = [r.get("response_difference_pct", 0.0) for r in results if "response_difference_pct" in r]
    f1s = [r.get("f1_score", 0.0) for r in results if "f1_score" in r]
    precisions = [r.get("precision", 0.0) for r in results if "precision" in r]
    recalls = [r.get("recall", 0.0) for r in results if "recall" in r]
    accuracies = [r.get("accuracy", 0.0) for r in results if "accuracy" in r]

    return {
        "total_photos": total,
        "successful_photos": successful,
        "failed_photos": failed,
        "success_rate_pct": round(success_rate, 2),
        "avg_semantic_similarity_pct": round(sum(sem_sims) / len(sem_sims), 2) if sem_sims else 0.0,
        "avg_response_difference_pct": round(sum(diff_pcts) / len(diff_pcts), 2) if diff_pcts else 0.0,
        "avg_f1_score": round(sum(f1s) / len(f1s), 2) if f1s else 0.0,
        "avg_precision": round(sum(precisions) / len(precisions), 2) if precisions else 0.0,
        "avg_recall": round(sum(recalls) / len(recalls), 2) if recalls else 0.0,
        "avg_accuracy": round(sum(accuracies) / len(accuracies), 2) if accuracies else 0.0,
    }
