# Pet-Plant Performance Evaluation Suite & Bruno Guide

A self-contained evaluation harness and endpoint testing suite for the Pet-Plant AI pipeline.
All scenario definitions, golden ground truths, botanical criteria, test plant photos, and Bruno API collections are version-controlled in the repository.

---

## Table of Contents

1. [Overview &amp; Evaluation Scopes](#1-overview--evaluation-scopes)
2. [Quick Start](#2-quick-start)
3. [Batch Photo Evaluation Engine](#3-batch-photo-evaluation-engine)
4. [Data Ingestion &amp; Pasting Guide](#4-data-ingestion--pasting-guide)
5. [Live HTTP vs. In-Memory Execution](#5-live-http-vs-in-memory-execution)
6. [Database Fixture Lifecycle (`setup-fixtures` &amp; `cleanup-fixtures`)](#6-database-fixture-lifecycle)
7. [Bruno API Collection (`bruno/`)](#7-bruno-api-collection)
8. [Active Model Lineage Tracking](#8-active-model-lineage-tracking)
9. [Automated Test Suite](#9-automated-test-suite)
10. [Directory Structure](#10-directory-structure)

---

## 1. Overview & Evaluation Scopes

The evaluation harness validates accuracy, schema conformance, quantitative text similarity/difference, and end-to-end multi-day lifecycle behavior across 3 scopes:

| Scope          | Target Component      | What It Validates                                                                                                                    | Key Datasets                                          |
| -------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------- |
| `vlm`        | Visual Language Model | Diagnostic assessment accuracy, structured symptoms, probe questions, text similarity & difference %, batch photo pass rate          | `datasets/vlm/scenarios.json`, `datasets/images/` |
| `llm`        | Care Advice (LLM)     | 3NF care plan schema conformance, action grounding in fired probes, action alignment %, text similarity & difference %               | `datasets/llm/advice_cases.json`                    |
| `end_to_end` | Complete System       | Multi-day pipeline lifecycle: photo upload via `/capture` → assessment → rules → advice → companion state envelope conformance | `datasets/end_to_end/scenarios.json`                |

---

## 2. Quick Start

Run the evaluation commands using `uv run python -m evaluation.scripts.cli`:

```bash
# Run all scopes (fast mode for smoke testing)
uv run python -m evaluation.scripts.cli run --fast

# Run the complete test suite across all multi-day scenarios
uv run python -m evaluation.scripts.cli run

# Run a specific scope only
uv run python -m evaluation.scripts.cli run --scope vlm
uv run python -m evaluation.scripts.cli run --scope llm
uv run python -m evaluation.scripts.cli run --scope end_to_end

# Run with automated post-run database cleanup
uv run python -m evaluation.scripts.cli run --cleanup

# Validate all manifest schemas without executing model calls
uv run python -m evaluation.scripts.cli validate

# Clean older evaluation reports
uv run python -m evaluation.scripts.cli clean --yes
```

---

## 3. Batch Photo Evaluation Engine

The evaluation suite includes a **Batch Photo Criteria Engine** designed for testing multiple plant photos simultaneously:

- Discovers all photos in a directory.
- Evaluates each photo against health criteria, symptom detection, and probe questions.
- Tracks individual **pass / fail** counts.
- Computes **aggregate averages across all photos** (Average Similarity %, Average Difference %, Average $F_1$, Precision, Recall, Accuracy).

### How to Run Batch Photo Evaluation

```bash
# 1. Run against the default images directory (evaluation/datasets/images/)
uv run python -m evaluation.scripts.cli evaluate-photos

# 2. Run against your own custom folder of photos
uv run python -m evaluation.scripts.cli evaluate-photos --images-dir /path/to/your/photos

# 3. Run with a specific ground-truth criteria manifest
uv run python -m evaluation.scripts.cli evaluate-photos --manifest evaluation/datasets/vlm/scenarios.json
```

### Adding New Photos for Future Testing

1. **Drop Images:** Place any `.jpg`, `.jpeg`, `.png`, or `.webp` files into:

   ```text
   evaluation/datasets/images/
   ```
2. **(Optional) Add Specific Criteria:** If you want custom ground-truth symptoms or probe answers for your new photos, add a case entry into:

   ```text
   evaluation/datasets/vlm/scenarios.json
   ```

   Reference the template provided in `evaluation/datasets/vlm/manifest_template.json`:

   ```json
   {
     "id": "VLM-CUSTOM-001",
     "species_code": "monstera_deliciosa",
     "image_path": "evaluation/datasets/images/my_plant.jpg",
     "description": "Monstera with lower leaf yellowing",
     "expected_response": {
       "health_status": "possibly_unhealthy",
       "assessment": "Lower leaves show yellowing consistent with overwatering.",
       "probe_answer": "yes"
     }
   }
   ```
3. **Inspect Output:** Run `uv run python -m evaluation.scripts.cli evaluate-photos`. You will receive a summary table:

   ```text
   =================================================================
   BATCH PHOTO CRITERIA EVALUATION REPORT
   =================================================================
   Total Photos Evaluated: 7
   Successful Photos:      7  (100.0% pass rate)
   Failed Photos:          0
   -----------------------------------------------------------------
   AVERAGE METRIC RESULTS ACROSS ALL PHOTOS:
     - Average Semantic Similarity:  95.11%
     - Average Response Difference:  4.89%
     - Average Structured F1 Score:  100.00%
     - Average Precision:            100.00%
     - Average Recall:               100.00%
     - Average Accuracy:             100.00%
   =================================================================
   ```

---

## 4. Data Ingestion & Pasting Guide

This section is your reference guide for **where to paste real data and photos** into the repository to make evaluations realistic and customized to your plants.

### Quick Reference: Where to Paste What

| Data Type                         | Target Destination File / Directory                  | What You Put There                                                              |
| --------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------- |
| **Plant Photos**            | `evaluation/datasets/images/`                      | Raw `.jpg`, `.jpeg`, `.png`, or `.webp` files from your phone or camera |
| **VLM Ground Truth**        | `evaluation/datasets/vlm/scenarios.json`           | Botanical probe questions, expected diagnoses, and ground-truth symptoms        |
| **LLM Care Advice**         | `evaluation/datasets/llm/advice_cases.json`        | Plant species, observed symptoms, and expected 3NF care plan actions            |
| **Botanical Knowledge**     | `sample/knowldge/<species_name>.md`                | Care instructions, watering intervals, light levels, and probe guidelines       |
| **Multi-Day E2E Scenarios** | `evaluation/datasets/end_to_end/scenarios/`        | Progressive daily observations over multi-day plant lifecycles                  |
| **E2E Golden Outputs**      | `evaluation/datasets/end_to_end/expected_outputs/` | Golden decisions (`NO_ACTION`, `CARE_ADVICE_REQUIRED`) per day              |

---

### A. How to Paste Photos

1. Copy your plant image files directly into:
   ```text
   evaluation/datasets/images/
   ```
2. **Recommended File Naming:** Use `<species>_<condition>.jpg`, for example:
   - `monstera_overwatered.jpg`
   - `pothos_sun_scorch.jpg`
   - `peace_lily_healthy.jpg`
   - `fiddle_leaf_fig_browning.jpg`
3. Supported image formats: `.jpg`, `.jpeg`, `.png`, `.webp`.
4. No image preprocessing is needed — the evaluation engine inspects resolution, blur, and brightness automatically.

---

### B. How to Paste VLM Assessment Ground Truth

Open [`evaluation/datasets/vlm/scenarios.json`](datasets/vlm/scenarios.json) and paste a new test case object into the `"cases"` array:

```json
{
  "id": "VLM-CASE-006",
  "species_code": "monstera_deliciosa",
  "image_path": "evaluation/datasets/images/monstera_overwatered.jpg",
  "description": "Monstera with lower leaf yellowing from overwatering",
  "probe_context": {
    "slug": "overwatering.widespread_yellowing_of",
    "care_need": "overwatering",
    "question": "Does the Monstera show signs of widespread yellowing of lower leaves?",
    "worse_looks_like": "Multiple older lower leaves nearest the soil turn bright solid yellow.",
    "better_looks_like": "Lower leaves maintain the exact same deep green color as the upper canopy."
  },
  "expected_response": {
    "health_status": "possibly_unhealthy",
    "assessment": "Multiple lower leaves exhibit solid yellow discoloration simultaneously, characteristic of prolonged soil moisture. Pattern is consistent with overwatering stress affecting the oldest foliage first.",
    "probe_answer": "yes",
    "confidence": 0.88
  },
  "actual_response": {
    "health_status": "possibly_unhealthy",
    "assessment": "Lower leaves near the soil line show uniform yellowing, suggesting the root zone has been consistently wet.",
    "probe_answer": "yes",
    "confidence": 0.85
  }
}
```

> **Tip:** If testing a live model, leave `actual_response` empty or omitted — the runner will populate it with the live model's verdict!

---

### C. How to Paste LLM Care Advice Data

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

### D. How to Paste Botanical Species Knowledge

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

### E. How to Verify Your Pasted Data

After pasting your photos or JSON cases, run these two commands to confirm everything is valid and working:

```bash
# 1. Schema check (makes sure your JSON syntax and mandatory keys are 100% correct)
uv run python -m evaluation.scripts.cli validate

# 2. Batch photo test (evaluates all images and prints pass/fail rate + averages)
uv run python -m evaluation.scripts.cli evaluate-photos
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

### Post-Run Auto Cleanup

Append `--cleanup` to any evaluation run to automatically tear down test fixtures after execution:

```bash
uv run python -m evaluation.scripts.cli run --cleanup
```

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

## 8. Active Model Lineage Tracking

All evaluation runs record the active AI models in use. Reports generated in `evaluation/reports/latest/summary.md` and `summary.json` prominently feature the **Active Models & Environment** table:

| Role                      | Model / Setting                              |
| ------------------------- | -------------------------------------------- |
| **VLM Model**       | `gemini-2.5-flash (evaluated / simulated)` |
| **LLM Model**       | `gpt-4o-mini`                              |
| **Embedding Model** | `nomic-embed-text`                         |
| **Execution Mode**  | `in_memory` / `http`                     |

### Metrics & Formula Definitions

- **Semantic Similarity (%)**: Cosine similarity via Ollama `nomic-embed-text` embeddings (fallback: token vector cosine).
- **Response Difference (%)**: `(100 - (similarity) × 100)` where similarity ∈ [0.0, 1.0].
- **Structured JSON $F_1$ Score**: Harmonic mean of Precision and Recall on symptoms and probe questions:
  $$
  F_1 = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}
  $$

---

## 9. Automated Test Suite

Unit and integration tests for the evaluation harness are stored in `tests/test_evaluation_suite.py`:

```bash
uv run pytest tests/test_evaluation_suite.py
```

This verifies:

- Manifest schema validation
- Quantitative similarity and difference mathematics
- VLM structured classification metrics ($F_1$, Precision, Recall, Accuracy)
- Batch photo evaluation engine and averaging calculations
- In-process HTTP client and FastAPI auth barriers
- Database fixture seeding and cascading teardown

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
│   ├── images/                        # Test plant photos (monstera, peace lily, etc.)
│   ├── vlm/                           # VLM scenarios & manifest templates
│   ├── llm/                           # LLM care advice test cases
│   └── end_to_end/                    # Multi-day lifecycle scenario definitions
├── vlm/
│   ├── run.py                         # VLM runner & batch photo evaluator
│   └── metrics.py                     # Precision, Recall, F1, Accuracy calculator
├── llm/
│   └── run.py                         # LLM care advice runner
├── end_to_end/
│   ├── run.py                         # End-to-end multi-day scenario runner
│   └── metrics.py                     # SLA latency and envelope compliance
├── scripts/
│   ├── cli.py                         # Unified evaluation CLI
│   └── cleanup.py                     # Safe report directory cleaner
└── reports/
    └── latest/                        # Symlink / mirror of most recent report
```
