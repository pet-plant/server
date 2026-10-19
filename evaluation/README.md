# Pet-Plant Performance Evaluation Suite & Bruno Guide

A self-contained evaluation harness and endpoint testing suite for the Pet-Plant AI pipeline.
All scenario definitions, golden ground truths, botanical criteria, test plant photos, and Bruno API collections are version-controlled in the repository.

---

## Table of Contents

1. [Overview & Evaluation Scopes](#1-overview--evaluation-scopes)
2. [Quick Start](#2-quick-start)
3. [VLM Final Dataset Evaluation Engine](#3-vlm-final-dataset-evaluation-engine)
4. [Data Ingestion & Pasting Guide](#4-data-ingestion--pasting-guide)
5. [Live HTTP vs. In-Memory Execution](#5-live-http-vs-in-memory-execution)
6. [Database Fixture Lifecycle (`setup-fixtures` & `cleanup-fixtures`, `--cleanup`)](#6-database-fixture-lifecycle)
7. [Bruno API Collection (`bruno/`)](#7-bruno-api-collection)
8. [Active Model Lineage Tracking & Metrics](#8-active-model-lineage-tracking--metrics)
9. [Automated Test Suite](#9-automated-test-suite)
10. [Directory Structure](#10-directory-structure)

---

## 1. Overview & Evaluation Scopes

The evaluation harness validates accuracy, schema conformance, quantitative text similarity/difference, and end-to-end multi-day lifecycle behavior across 3 scopes:

| Scope          | Target Component      | What It Validates                                                                                                                              | Key Datasets                                          |
| -------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `vlm`          | Visual Language Model | Diagnostic condition assessment (`healthy`/`unhealthy`), multi-label symptom classification, binary confusion matrix, per-species breakdown   | `datasets/final/eval.jsonl`, `datasets/final/species.json`, `datasets/final/images/` |
| `llm`          | Care Advice (LLM)     | 3NF care plan schema conformance, action grounding in fired probes, action alignment %, text similarity & difference %                         | `datasets/llm/advice_cases.json`                      |
| `end_to_end`   | Complete System       | Multi-day pipeline lifecycle: photo upload via `/capture` → assessment → rules → advice → companion state envelope conformance           | `datasets/end_to_end/scenarios.json`                  |

---

## 2. Quick Start

Run evaluation commands using `uv run python -m evaluation.scripts.cli`:

```bash
# Run all scopes (fast mode for smoke testing)
uv run python -m evaluation.scripts.cli run --fast

# Run the complete test suite (includes 505-sample final VLM dataset, LLM advice, and E2E multi-day scenarios)
uv run python -m evaluation.scripts.cli run

# Run with automated post-run database fixture cleanup
uv run python -m evaluation.scripts.cli run --cleanup

# Run a specific scope only
uv run python -m evaluation.scripts.cli run --scope vlm
uv run python -m evaluation.scripts.cli run --scope llm
uv run python -m evaluation.scripts.cli run --scope end_to_end

# Standalone final dataset VLM evaluation
uv run python -m evaluation.scripts.cli evaluate-final --limit 10
uv run python -m evaluation.scripts.cli evaluate-final --use-mock
uv run python -m evaluation.scripts.cli evaluate-final --predictions-file evaluation/reports/final_predictions.jsonl

# Validate all manifest schemas and final dataset files without executing model calls
uv run python -m evaluation.scripts.cli validate

# Clean older evaluation reports
uv run python -m evaluation.scripts.cli clean --yes
```

---

## 3. VLM Final Dataset Evaluation Engine

The VLM evaluation scope evaluates the model on a benchmark of **505 human-reviewed images across 10 indoor plant species** located in `evaluation/datasets/final/`.

### Dataset Structure

```text
evaluation/datasets/final/
├── eval.jsonl       # 505 ground-truth records (image_path, species_code, health_status, symptoms)
├── species.json     # 10 species metadata profiles with allowed symptoms
└── images/          # JPG images organized by species and health status
```

Each sample in `eval.jsonl` contains:
```json
{
  "id": "monstera_deliciosa_unhealthy_0042",
  "image_path": "images/monstera_deliciosa/unhealthy_0042.jpg",
  "species_code": "monstera_deliciosa",
  "ground_truth": {
    "health_status": "unhealthy",
    "symptoms": ["leaf_yellowing", "brown_leaf_tips"]
  }
}
```

### What Is Evaluated

1. **Binary Condition Classification (`health_status`):**
   - Classes: `healthy` vs `unhealthy`
   - Metrics: **Accuracy**, **Precision**, **Recall**, **$F_1$ Score**
   - Complete Confusion Matrix: True Positives (TP), True Negatives (TN), False Positives (FP), False Negatives (FN)

2. **Multi-Label Symptom Classification (`symptoms`):**
   - Symptoms: `leaf_yellowing`, `wilting`, `brown_leaf_tips`, `leaf_spots`, etc.
   - Metrics: **Micro $F_1$**, **Macro $F_1$**, Micro Precision/Recall, Macro Precision/Recall
   - Per-symptom breakdown with support counts and per-species accuracy slicing

3. **Incremental Prediction Caching:**
   - Predictions are checkpointed to `evaluation/reports/final_predictions.jsonl`.
   - If interrupted, re-running `--predictions-file evaluation/reports/final_predictions.jsonl` resumes without re-inferencing already completed images.

### How to Run VLM Evaluation

```bash
# 1. Official VLM scope run (via full suite)
uv run python -m evaluation.scripts.cli run --scope vlm

# 2. Fast smoke test (first 5 samples using mock predictor)
uv run python -m evaluation.scripts.cli run --scope vlm --fast

# 3. Direct evaluation with a sample limit (e.g., 20 images)
uv run python -m evaluation.scripts.cli evaluate-final --limit 20

# 4. Instant re-scoring from an existing predictions file
uv run python -m evaluation.scripts.cli evaluate-final --predictions-file evaluation/reports/final_predictions.jsonl
```

---

## 4. Data Ingestion & Pasting Guide

This section is your reference guide for **where to paste real data and photos** into the repository to make evaluations realistic and customized to your plants.

### Quick Reference: Where to Paste What

| Data Type                         | Target Destination File / Directory                  | What You Put There                                                              |
| --------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Final VLM Dataset**             | `evaluation/datasets/final/`                         | 505 human-reviewed leaf images, `eval.jsonl`, and `species.json`                |
| **LLM Care Advice Cases**         | `evaluation/datasets/llm/advice_cases.json`          | Plant species, observed symptoms, and expected 3NF care plan actions            |
| **Botanical Knowledge Profiles**   | `sample/knowldge/<species_name>.md`                  | Care instructions, watering intervals, light levels, and visual symptom guides  |
| **Multi-Day E2E Scenarios**       | `evaluation/datasets/end_to_end/scenarios/`          | Progressive daily observations over multi-day plant lifecycles                  |
| **E2E Golden Outputs**            | `evaluation/datasets/end_to_end/expected_outputs/`   | Golden decisions (`NO_ACTION`, `CARE_ADVICE_REQUIRED`) per day                  |

---

### A. How to Add Images to the Final VLM Dataset

1. Place image files into the species subfolder:
   ```text
   evaluation/datasets/final/images/<species_code>/<image_name>.jpg
   ```
2. Append the ground-truth line to `evaluation/datasets/final/eval.jsonl`:
   ```json
   {"id": "monstera_deliciosa_unhealthy_0043", "image_path": "images/monstera_deliciosa/unhealthy_0043.jpg", "species_code": "monstera_deliciosa", "ground_truth": {"health_status": "unhealthy", "symptoms": ["leaf_yellowing"]}}
   ```
3. Run `uv run python -m evaluation.scripts.cli validate` to verify image paths and species codes.

---

### B. How to Paste LLM Care Advice Data

Open [`evaluation/datasets/llm/advice_cases.json`](datasets/llm/advice_cases.json) and paste a new case into the `"cases"` array:

```json
{
  "id": "CASE-ADVICE-006",
  "plant_id": "monstera-plant-01",
  "species_code": "monstera_deliciosa",
  "observations": [
    {
      "id": "obs-006",
      "timestamp": "2026-10-17T12:00:00Z",
      "health_status": "possibly_unhealthy",
      "symptoms": ["leaf_yellowing", "drooping_petioles"],
      "confidence": 0.88
    }
  ],
  "expected_care_plan": {
    "diagnosis": "overwatering",
    "status_label": "Soil Moisture Stress",
    "assessment": "Lower leaves show bright yellowing from saturated potting mix.",
    "actions": [
      {
        "priority": 1,
        "type": "inspect",
        "label": "Check Root Drainage",
        "action": "Ensure the planter drainage holes are not blocked and let the top 5cm of soil dry completely."
      },
      {
        "priority": 2,
        "type": "water",
        "label": "Withhold Watering",
        "action": "Pause all watering for 7-10 days until soil moisture drops to acceptable levels."
      }
    ]
  }
}
```

---

### C. How to Paste Botanical Species Knowledge

If you want to support a new plant species, create a Markdown file in:

```text
sample/knowldge/<species_name>.md
```

*Example structure:*

```markdown
# Sweet Basil (Ocimum basilicum)

## Care Profile
- **Watering:** Moderate (every 3-5 days when top 2cm dry)
- **Light:** High (6+ hours direct sunlight)
- **Soil:** Well-draining, rich loam

## Diagnoses & Symptoms
| Care Need | Visual Symptoms | Approved Actions |
|---|---|---|
| Water Deficit | Wilting stems, limp drooping leaves | Water thoroughly until water drains freely |
| Low Light | Stretched leggy stems, pale leaves | Relocate to sunnier south-facing window |
```

Run `uv run python -m evaluation.scripts.cli validate` to verify the botanical knowledge parser successfully registers the new species.

---

### D. How to Verify Your Pasted Data

After updating datasets, run:

```bash
# 1. Schema check (makes sure all JSON syntax, image paths, and keys are 100% correct)
uv run python -m evaluation.scripts.cli validate

# 2. Fast evaluation run across all scopes
uv run python -m evaluation.scripts.cli run --fast
```

---

## 5. Live HTTP vs. In-Memory Execution

The evaluation suite supports two execution modes:

### A. In-Memory Mode (`--mode in_memory`, Default)

- Runs with fast, isolated in-memory SQLite databases and mocked responses.
- Requires zero background daemons. Ideal for rapid development and headless CI pipelines:
  ```bash
  uv run python -m evaluation.scripts.cli run --mode in_memory
  ```

### B. HTTP Endpoint Mode (`--mode http`)

- Hits live FastAPI endpoints or in-process ASGI via `EvaluationHttpClient`.
- Ingests test photos via `POST /capture/devices/me/frames`, triggers pipeline runs via `POST /orchestrator/runs`, and polls `GET /companion/devices/me/state`:
  ```bash
  uv run python -m evaluation.scripts.cli run --scope end_to_end --mode http
  ```

---

## 6. Database Fixture Lifecycle

To test real API endpoints without leaving test artifacts in PostgreSQL:

### Seed Test Fixtures

Creates baseline botanical species catalog, bootstrap admin user, dedicated test user (`test_evaluator@example.com`), paired edge device, and registered test plant:

```bash
uv run python -m evaluation.scripts.cli setup-fixtures
```

### Clean Up Test Fixtures

Deletes all test records, captures, care plans, observations, and devices in strict foreign-key order:

```bash
uv run python -m evaluation.scripts.cli cleanup-fixtures
```

### Post-Run Auto Cleanup (`--cleanup`)

Append `--cleanup` to any evaluation run to automatically tear down test fixtures after execution:

```bash
uv run python -m evaluation.scripts.cli run --cleanup
```

When `--cleanup` is specified, the CLI invokes `cleanup_fixtures()` immediately following report generation, ensuring the database is left clean even after full integration runs.

---

## 7. Bruno API Collection (`bruno/`)

The repository includes a Git-versioned **Bruno collection** in `bruno/`.

### Opening in Bruno GUI

1. Open the [Bruno](https://www.usebruno.com/) desktop application.
2. Click **Open Collection** and select the `bruno/` directory in the repository.
3. Select the **Local** environment (`bruno/environments/local.bru`).

### Collection Folder Structure

- `01_prerequisites/`: Health check verification (`GET /health`)
- `02_auth_and_pairing/`: User registration, login, start pairing, approve pairing, device token exchange, plant registration
- `03_capture/`: Edge device frame upload (`POST /capture/devices/me/frames`)
- `04_orchestrator/`: Pipeline run trigger (`POST /orchestrator/runs`) and run polling
- `05_companion_scenarios/`:
  - `01_unauthenticated.bru` (401 check)
  - `02_user_jwt_missing_plant_id.bru` (400 check)
  - `03_user_jwt_happy_path.bru` (200 envelope check)
  - `04_device_steady_state.bru` (200 device token check)
  - `05_unbound_device_error.bru` (404 / 409 check)
- `99_cleanup/`: Teardown test data script

---

## 8. Active Model Lineage Tracking & Metrics

All evaluation runs record the active AI models in use. Reports generated in `evaluation/reports/latest/summary.md` and `summary.json` prominently feature the **Active Models & Environment** table:

| Role                      | Model / Setting                              |
| ------------------------- | -------------------------------------------- |
| **VLM Model**             | `internvl3_5-2b` (local/evaluated)           |
| **LLM Model**             | `gpt-4o-mini` / `llama3.2`                   |
| **Embedding Model**       | `nomic-embed-text`                           |
| **Execution Mode**        | `in_memory` / `http`                         |

### Metrics & Formula Definitions

- **Health Status Accuracy (%)**:
  $$
  \text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}
  $$
- **Health Status $F_1$ Score**:
  $$
  F_1 = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}
  $$
- **Symptoms Micro $F_1$ Score**:
  Global aggregation of true positive, false positive, and false negative symptom detections across all 505 images.
- **Symptoms Macro $F_1$ Score**:
  Unweighted arithmetic mean of individual $F_1$ scores for each distinct symptom class (giving equal weight to rare symptoms).
- **Semantic Similarity (%)**:
  Cosine similarity via Ollama `nomic-embed-text` embeddings (fallback: token vector cosine).
- **Response Difference (%)**:
  $(100 - (\text{similarity}) \times 100)$ where $\text{similarity} \in [0.0, 1.0]$.
- **FE Envelope Compliance Rate**:
  Fraction of responses meeting the frontend companion state schema specifications ($100\%$ required).

---

## 9. Automated Test Suite

Unit and integration tests for the evaluation harness and the final dataset pipeline:

```bash
# Run all evaluation tests (33 tests)
uv run pytest tests/test_evaluation_suite.py tests/test_final_evaluation.py
```

This verifies:
- Validation of the 505-sample final dataset manifest (`eval.jsonl` and `species.json`)
- VLM prompt construction and structured prediction parsing
- Incremental prediction caching and resuming from disk
- Binary condition metrics, confusion matrices, and multi-label symptom metrics
- Quantitative similarity and difference mathematics
- In-process HTTP client and FastAPI auth barriers
- Database fixture seeding and cascading teardown (`--cleanup`)

---

## 10. Directory Structure

```text
evaluation/
├── README.md                          # Comprehensive guide (this file)
├── __init__.py                        # Python package initialization
├── common/                            # Shared utilities
│   ├── config.py                      # EvaluationConfig loader & thresholds
│   ├── http_client.py                 # Live and in-process HTTP client adapter
│   ├── loaders.py                     # Manifest validation schemas
│   ├── metrics.py                     # Similarity, difference, percentile math
│   ├── mock_model.py                  # Mock chat model for isolated testing
│   ├── reporting.py                   # Markdown, JSON, and JSONL report generator
│   └── sample_knowledge.py            # Botanical knowledge parser & seeder
├── config/
│   └── default.json                   # Configuration parameters & SLA thresholds
├── datasets/
│   ├── final/                         # 505 human-reviewed images across 10 species
│   │   ├── eval.jsonl                 # Ground truth records
│   │   ├── species.json               # 10 plant species metadata profiles
│   │   └── images/                    # Leaf images organized by species/condition
│   ├── llm/                           # LLM care advice test cases
│   └── end_to_end/                    # Multi-day lifecycle scenario definitions
├── vlm/
│   ├── run.py                         # Official VLM runner (evaluates final dataset)
│   ├── final_dataset.py               # Dataset loader & manifest validator
│   ├── predictor.py                   # VLM prompt builder, parser, & disk checkpointing
│   └── metrics.py                     # Health status & multi-label symptom metrics
├── llm/
│   └── run.py                         # LLM care advice runner
├── end_to_end/
│   ├── run.py                         # End-to-end multi-day scenario runner
│   └── metrics.py                     # SLA latency and envelope compliance
├── scripts/
│   ├── cli.py                         # Unified evaluation CLI (run, evaluate-final, etc.)
│   └── cleanup.py                     # Safe report directory cleaner
└── reports/
    └── latest/                        # Symlink / mirror of most recent report
```
