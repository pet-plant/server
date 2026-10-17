# End-to-End Pipeline Evaluation Dataset Guide

This directory contains the self-contained evaluation suite, scenario specifications, dedicated plant imagery, and golden expected outputs for the **end_to_end** scope of the Pet-Plant system.

---

## Directory Architecture

```
evaluation/datasets/end_to_end/
├── scenarios.json              # Main scenario manifest defining test cases and pass/fail criteria
├── images/                     # Dedicated end-to-end plant images (isolated from raw images)
│   ├── healthy_baseline.jpg    # Vibrant green baseline foliage (720x1280)
│   ├── healthy_day2.jpg        # Stable healthy day 2 follow-up (720x1280)
│   ├── healthy_day3.jpg        # Stable healthy day 3 follow-up (720x1280)
│   ├── yellowing_moderate.jpg  # Mild/moderate chlorosis symptom (720x845)
│   ├── wilting_severe.jpg      # Severe wilt and distress (1200x896)
│   ├── recovery_improving.jpg  # Regreening / recovering foliage (720x1280)
│   ├── recovery_healthy.jpg    # Full recovery back to health (720x1280)
│   ├── drought_desiccated.jpg  # Severe chronic stress (860x1024)
│   └── drought_sequence.jpg    # Extended distress sequence (720x1280)
├── scenarios/                  # Scenario observation inputs
│   ├── no_change.json
│   ├── new_symptom.json
│   ├── severity_increase.json
│   ├── improvement.json
│   ├── health_status_change.json
│   └── milestone_lifecycle.json
├── expected_outputs/           # Golden expected decisions, care plans, and contracts
│   ├── scenario_no_change.json
│   ├── scenario_new_symptom.json
│   ├── scenario_severity_increase.json
│   ├── scenario_improvement.json
│   ├── scenario_health_status_change.json
│   └── scenario_multi_day.json
└── responses/                  # Mock LLM & Companion response fixtures
    ├── advice/
    └── companion/
```

---

## Why a Dedicated Images Folder?

The `evaluation/datasets/end_to_end/images/` directory is strictly isolated from `evaluation/datasets/images/`.

All images in this dedicated folder are guaranteed to:
1. Pass edge capture quality gates (resolution $\ge 640\times 480$, blur variance $> 50$, brightness $\in [40, 220]$).
2. Pass green plant segmentation and aspect-ratio normalization in `capture.vision.preprocess`.
3. Provide consistent visual sequences representing realistic botanical transitions across consecutive calendar days.

---

## Scenarios & Expected Results

| Scenario Name | Days | Images Passed Through | Health Trajectory | Expected Decisions | Key Milestones | Expected Care Plan |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| **`no_change`** | 2 | Day 1: `healthy_baseline.jpg`<br>Day 2: `healthy_day2.jpg` | healthy $\rightarrow$ healthy | `["NO_ACTION", "NO_ACTION"]` | None | `null` (zero actions) |
| **`new_symptom`** | 2 | Day 1: `healthy_baseline.jpg`<br>Day 2: `yellowing_moderate.jpg` | healthy $\rightarrow$ possibly_unhealthy | `["NO_ACTION", "CARE_ADVICE_REQUIRED"]` | `first_symptom` (Day 2) | 2 actions (`inspect`, `other`) |
| **`severity_increase`** | 2 | Day 1: `yellowing_moderate.jpg`<br>Day 2: `wilting_severe.jpg` | possibly_unhealthy $\rightarrow$ unhealthy | `["CARE_ADVICE_REQUIRED", "CARE_ADVICE_REQUIRED"]` | `first_symptom`, `health_crisis` | 4 prioritized actions (`inspect`, `other`, `move`) |
| **`improvement`** | 2 | Day 1: `wilting_severe.jpg`<br>Day 2: `recovery_improving.jpg` | unhealthy $\rightarrow$ possibly_unhealthy | `["CARE_ADVICE_REQUIRED", "NO_ACTION"]` | `first_symptom` | Day 1: 4 actions<br>Day 2: `null` (recovery clears plan) |
| **`health_status_change`** | 2 | Day 1: `healthy_baseline.jpg`<br>Day 2: `yellowing_moderate.jpg` | healthy $\rightarrow$ possibly_unhealthy | `["NO_ACTION", "CARE_ADVICE_REQUIRED"]` | `first_symptom` | 3 actions (`water`, `inspect`, `move`) |
| **`multi_day`** (`milestone_lifecycle`) | 6 | Day 1: `healthy_baseline.jpg`<br>Day 2: `yellowing_moderate.jpg`<br>Day 3: `wilting_severe.jpg`<br>Day 4: `drought_desiccated.jpg`<br>Day 5: `drought_sequence.jpg`<br>Day 6: `recovery_healthy.jpg` | healthy $\rightarrow$ possibly_unhealthy $\rightarrow$ unhealthy $\times 3 \rightarrow$ healthy | `["NO_ACTION", "CARE_ADVICE_REQUIRED", "CARE_ADVICE_REQUIRED", "NO_ACTION", "NO_ACTION", "NO_ACTION"]` | `first_symptom` (D2)<br>`health_crisis` (D3)<br>`severe_episode` (D5)<br>`full_recovery` (D6) | Day 2 & 3: 4 actions<br>Days 4–6: `null` |

---

## Validation & Verification

### 1. Validate Schema Integrity
```bash
uv run python -m evaluation.scripts.cli validate
```

### 2. Run End-to-End Evaluation (In-Memory)
```bash
uv run python -m evaluation.scripts.cli run --scope end_to_end
```

### 3. Run End-to-End Evaluation (Live HTTP against Docker)
```bash
uv run python -m evaluation.scripts.cli run --scope end_to_end --mode http
```
