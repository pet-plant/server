# VLM Plant Symptom Evaluation Dataset Guide

> **Status:** Pending real-world human/botanist ground truth labeling (Item H2 in Human Action Backlog).

This directory contains scenario manifests, templates, and specifications for the **Visual Language Model (VLM)** plant symptom assessment evaluation.

---

## Evaluation Architecture

The VLM evaluation scope evaluates model perception across two complementary engines:
1. **Paired Frame Scenario Evaluation:** Compares the VLM output on temporal frame pairs ($t-1$ and $t$) against verified ground truth in `scenarios.json`.
2. **Batch Photo Evaluation Engine:** Assesses raw plant photos in `evaluation/datasets/images/` for capture quality gates (resolution, blur, brightness, plant mask) and botanical criteria classification (Precision, Recall, F1, Accuracy, Semantic Similarity).

---

## Dataset Requirements

1. **Independent Ground Truth:** Labels must be independently verified by plant specialists/botanists, not generated or copied from the model's own predictions.
2. **Paired Frames:** Image 1 (previous day $t-1$) and Image 2 (current day $t$).
3. **Supported Symptoms:**
   - `leaf_yellowing`
   - `brown_edges`
   - `drooping`
   - `curling`
   - `visible_damage`
   - `discoloration`
   - `other`
4. **Severity Levels:**
   - `mild`
   - `moderate`
   - `severe`
5. **Health Statuses:**
   - `healthy`
   - `possibly_unhealthy`
   - `unhealthy`
6. **Probe Answers:**
   - `yes`
   - `no`
   - `uncertain`

---

## Dataset Layout & Storage

- **Active Manifest:** `evaluation/datasets/vlm/scenarios.json` (authoritative dataset loaded by CLI runner).
- **Template for New Cases:** `evaluation/datasets/vlm/manifest_template.json` (sample schema for botanists).
- **Image Directory:** Photos are placed into `evaluation/datasets/images/` (e.g. `evaluation/datasets/images/monstera_yellowing.jpg`).

---

## Adding New Ground-Truth Cases

To populate new verified evaluation cases:
1. Place photo pairs into `evaluation/datasets/images/`.
2. Ensure image resolution is $\ge 640\times 480$, blur variance $> 50$, and brightness is within $[40, 220]$.
3. Add the case to `evaluation/datasets/vlm/scenarios.json` (or use `manifest_template.json` as a guide) with:
   - `id`: Unique identifier (e.g. `VLM-CASE-034`)
   - `species_code`: Botanical species (e.g. `monstera_deliciosa`, `peace_lily`)
   - `image_path`: Path relative to server root (e.g. `evaluation/datasets/images/peace_lily_20261011_152541.jpg`)
   - `probe_context`: Associated botanical check (`slug`, `care_need`, `question`, `better_looks_like`, `worse_looks_like`)
   - `expected_response`: Verified `health_status`, `assessment`, `probe_answer`, and `confidence`.
4. Validate schema compliance:
   ```bash
   uv run python -m evaluation.scripts.cli validate
   ```

---

## Running VLM Evaluations

Run VLM evaluation via the unified evaluation CLI:

```bash
# Validate dataset schemas
uv run python -m evaluation.scripts.cli validate

# Run complete VLM evaluation suite
uv run python -m evaluation.scripts.cli run --scope vlm

# Fast mode (first 2 cases only)
uv run python -m evaluation.scripts.cli run --scope vlm --fast

# Execute against live HTTP endpoints
uv run python -m evaluation.scripts.cli run --scope vlm --mode http
```
