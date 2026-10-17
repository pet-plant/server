# Pet-Plant Automated Performance Evaluation Suite — Specification

- **Document Version:** 1.1.0
- **Status:** Draft / Specification
- **Target Location:** `evaluation/`
- **Date:** 2026-10-17

---

## 1. Executive Summary

This specification outlines the technical design for an automated performance evaluation test suite for `pet-plant-server`. Following thorough inspection of the active codebase, all unresolved implementation questions ("PENDING CODEBASE INSPECTION" items from the initial brief) have been concrete-mapped to the actual production modules, contracts, schemas, and fixtures.

The evaluation suite:
1. Resides under a dedicated top-level `evaluation/` directory.
2. Evaluates five distinct scopes: **Image Preprocessing**, **VLM Symptom Analysis**, **LLM Advice Generation**, **Plant-Health Tracking**, and **End-to-End System Scenarios**.
3. Supports a unified command-line interface (`uv run python -m evaluation.scripts.cli run`) as well as isolated scope execution (`--scope <name>`).
4. Operates offline and deterministically by default: zero external network calls, zero surprise paid API charges.
5. Employs a strict allowlist-based cleanup command (`--dry-run` by default, `--yes` to execute) that is structurally restricted to `evaluation/reports/`.
6. Enforces strict honesty: missing models, unannotated real-world datasets, or unconfigured credentials are explicitly reported as `SKIPPED`, never as fabricated passes.
7. Explicitly catalogues and tracks **all items requiring human domain expertise or data labeling** in a dedicated **Human Action Backlog** ([Section 6](#6-human-action--labeling-backlog-todos)).

---

## 2. Codebase Inspection & Resolved Technical Mapping

| Initial Brief Item | Status in Brief | Resolved Codebase Reality & Technical Choice |
|---|---|---|
| **Language & Environment** | *Pending* | **Python 3.12+ (active: Python 3.13.7)**, managed with `uv` (`pyproject.toml`, `uv.lock`). Runner is `pytest` with `pytest-asyncio`. |
| **CLI Invocation** | *Pending* | Standard Python module entry point: `uv run python -m evaluation.scripts.cli [run\|validate\|clean]`. |
| **Image Preprocessing Scope** | *Pending* | Targets `capture.vision.quality.assess_image_quality` (`QualityConfig` $\to$ `QualityResult`) and `capture.vision.preprocess.preprocess_image` (`PreprocessConfig` $\to$ `PreprocessResult`). Real labels evaluate blur, brightness, width/height defects, and plant crop bounding box. |
| **VLM Symptom Analysis Scope** | *Pending* | Schema: `mlops.assessment.schemas.RunObservation` (`current_observations`: `ObservationType`, `Severity`, `probe_findings`). Defined symptom types: `leaf_yellowing`, `brown_edges`, `drooping`, `curling`, `visible_damage`, `discoloration`, `other`. Severities: `mild`, `moderate`, `severe`. |
| **LLM Advice Scope** | *Pending* | Targets `mlops.advice.runtime.generate_advice` and `advice.service.generate_for_plant`. Enforces 3NF action structure (`water`, `move`, `inspect`, `other`), priority ordering ($1, 2, \dots$), prohibited claim verification, and token overlap/ROUGE against golden care plans. LLM-as-a-judge is opt-in (`--enable-judge`). |
| **Plant-Health Tracking Scope** | *Pending* | Targets `assessment.service.evaluate_rules` and `detect_milestones`. Evaluates multi-day decision transitions (`NO_ACTION`, `CARE_ADVICE_REQUIRED`, `REQUEST_MORE_INFORMATION`), false deterioration rate, and milestone event lifecycle. |
| **End-to-End Scope** | *Pending* | Reuses the 6 scenario datasets and golden assertions in `fixtures/mock_llm_for_llm_pipeline_integration/` to evaluate complete multi-day runs through `orchestrator.worker.execute_run`, verifying pipeline transitions, decisions, and Frontend response envelopes. |
| **Report Formats** | *Pending* | Timestamped runs in `evaluation/reports/<run-id>/` containing `summary.json`, `summary.md`, and per-scope `.jsonl` files. |
| **Cleanup Allowlist** | *Pending* | Strictly locked to `<workspace>/evaluation/reports/`. Files named `.gitkeep` or `README.md` are preserved. Dry-run by default. |

---

## 3. Directory Structure

```text
evaluation/
├── README.md                           # Suite overview, usage commands, metric descriptions
├── config/
│   └── default.json                    # Tunable evaluation thresholds and opt-in switches
├── datasets/
│   ├── README.md                       # Guide on schema formats and adding labeled examples
│   ├── image_preprocessing/
│   │   ├── manifest.json               # Manifest of test images and quality ground truth
│   │   └── samples/                    # Synthetic and fixture test images
│   ├── vlm/
│   │   ├── README.md                   # Pending dataset notice and instructions
│   │   └── manifest_template.json      # Ground truth symptom & severity schema template
│   ├── llm/
│   │   └── advice_cases.json           # Diagnostic context inputs & golden care plans
│   ├── plant_health_tracking/
│   │   └── tracking_sequences.json     # Multi-day observation sequences with expected decisions
│   └── end_to_end/
│       └── scenarios.json              # E2E pipeline scenarios with mandatory criteria specs
├── image_preprocessing/
│   ├── README.md
│   ├── metrics.py                      # Accuracy, precision, recall, F1 per quality defect
│   └── run.py                          # Quality classification and crop runner
├── vlm/
│   ├── README.md
│   ├── metrics.py                      # Multi-symptom precision, recall, macro-F1, severity match
│   └── run.py                          # VLM runner with graceful skip handling
├── llm/
│   ├── README.md
│   ├── metrics.py                      # Schema validity, action grounding, token overlap
│   ├── judge.py                        # Optional opt-in LLM judge (disabled by default)
│   └── run.py                          # Care advice evaluation runner
├── plant_health_tracking/
│   ├── README.md
│   ├── metrics.py                      # Trend accuracy, false deterioration rate, milestone metrics
│   └── run.py                          # Deterministic event engine & milestone lifecycle runner
├── end_to_end/
│   ├── README.md
│   ├── metrics.py                      # Scenario success rate, stage pass rate, latency stats
│   └── run.py                          # Full pipeline scenario execution runner
├── common/
│   ├── config.py                       # Configuration loader and models
│   ├── loaders.py                      # Manifest loaders with strict schema validation
│   ├── metrics.py                      # Shared metric algorithms (confusion matrix, F1)
│   └── reporting.py                    # JSONL logger, summary.json, and summary.md generator
├── scripts/
│   ├── cli.py                          # Unified CLI entry point
│   └── cleanup.py                      # Allowlist-restricted safe cleanup script
└── reports/
    └── .gitkeep
```

---

## 4. Evaluation Scope Specifications & Formulas

### Scope A: Image Preprocessing
* **Function Under Test:**
  * `capture.vision.quality.assess_image_quality(image, config)`
  * `capture.vision.preprocess.preprocess_image(source_image, config)`
* **Evaluated Defects:**
  * `image_too_narrow`, `image_too_short` (Resolution gate: $<640 \times 480$)
  * `image_too_dark` (Brightness gate: $<40.0$)
  * `image_too_bright` (Brightness gate: $>220.0$)
  * `image_too_blurry` (Blur score Laplacian variance: $<50.0$)
* **Candidate Metrics:**
  * $\text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}$
  * $\text{Precision}_{\text{defect}} = \frac{TP}{TP + FP}$, $\text{Recall}_{\text{defect}} = \frac{TP}{TP + FN}$, $\text{F1} = 2 \cdot \frac{P \cdot R}{P + R}$
  * $\text{Crop Success Rate} = \frac{\text{Successful Crops}}{\text{Valid Plant Images}} \times 100\%$
* > [!IMPORTANT]
  > **TODO (Human Action Required — Item H1):** Real device webcam photos across varying ambient room lighting and lens blur must be photographed and labeled by humans in `evaluation/datasets/image_preprocessing/manifest.json`. Initial test execution uses synthetic image fixtures.

### Scope B: VLM Plant-Image Analysis
* **Function Under Test:**
  * `mlops.assessment.runtime.run_probe(input_data)` / `mlops.assessment.aggregate.majority_vote`
* **Output Schema Contract:**
  * Observation Types: `leaf_yellowing`, `brown_edges`, `drooping`, `curling`, `visible_damage`, `discoloration`, `other`
  * Severities: `mild`, `moderate`, `severe`
  * Species Probe Checks: `yes`, `no`, `cannot_tell`
* **Candidate Metrics:**
  * Per-symptom Precision, Recall, and F1.
  * Macro-F1 across all symptom categories:
    $$\text{Macro-F1} = \frac{1}{N} \sum_{i=1}^N \text{F1}_i$$
  * Severity accuracy among true-positive detected symptoms:
    $$\text{Severity Accuracy} = \frac{\sum \mathbb{I}(\hat{s}_i = s_i^*)}{TP_{\text{symptoms}}}$$
* **Missing Dataset / Weights Policy:**
  * When local VLM weights (`models/internvl3_5-2b`) or vLLM endpoints are not configured, this scope records `SKIPPED (reason: VLM backend not configured or dataset pending)` and continues without failing the overall suite.
* > [!IMPORTANT]
  > **TODO (Human Action Required — Item H2):** Botanist / domain expert ground truth labeling of real plant photo pairs (Day $t-1$ and Day $t$) using `evaluation/datasets/vlm/manifest_template.json`. Labels must not be copied from model predictions.

### Scope C: LLM Health Assessment & Care Advice
* **Function Under Test:**
  * `mlops.advice.runtime.generate_advice(payload)`
  * `advice.service.generate_for_plant(session, plant_id, run_id)`
* **Deterministic Metrics:**
  * **Schema Conformance Rate:** Fraction of outputs passing `GeneratedCarePlan` validation.
  * **Action Grounding Rate:** Percentage of actions matching the prompt's `approved_actions` input list.
  * **Action Type Validity:** Percentage of actions assigned to `water | move | inspect | other`.
  * **Priority Monotonicity:** Strict ordering check ($1, 2, \dots$) without gaps or duplicates.
  * **Prohibited Claim Violations:** Flagging text claiming unverified fungal/bacterial causes not present in fired checks.
* **Semantic & Quantitative Difference Metrics:**
  * **Semantic Similarity (%):** Cosine similarity between expected and actual assessment embeddings via Ollama `nomic-embed-text`:
    $$\text{Similarity (\%)} = \text{similarity} \times 100\%$$
  * **Response Difference (%):** Quantifies divergence between expected standard and actual generated advice:
    $$\text{Difference (\%)} = (100 - (\text{similarity}) \times 100)$$
    (where $\text{similarity} \in [0.0, 1.0]$ is normalized cosine similarity).
  * **Token-level Similarity:** SequenceMatcher ratio and Jaccard token overlap against golden reference advice.
  * **Action Alignment Rate (%):** Jaccard set overlap of selected actions:
    $$\text{Action Alignment} = \frac{|\text{Actions}_{\text{expected}} \cap \text{Actions}_{\text{actual}}|}{|\text{Actions}_{\text{expected}} \cup \text{Actions}_{\text{actual}}|} \times 100\%$$

* **Optional LLM-as-a-Judge:**
  * Disabled by default. Enabled strictly via `--enable-judge`. Scores rubric on Factual Accuracy, Advice Suitability, and Completeness (1–5 scale).
* > [!IMPORTANT]
  > **TODO (Human Action Required — Item H3 & H4):**
  > 1. Expert review of golden reference advice texts and prohibited claims list in `evaluation/datasets/llm/advice_cases.json`.
  > 2. Deciding LLM judge model/provider (e.g. GPT-4o vs local Ollama) and provisioning judge API credentials before enabling `--enable-judge`.

### Scope D: Plant-Health Tracking
* **Function Under Test:**
  * `assessment.service.evaluate_rules(new_obs, prev_obs, confidence_threshold)`
  * `assessment.service.detect_milestones(new_obs, history, existing_milestones)`
* **Target Decisions:** `NO_ACTION`, `CARE_ADVICE_REQUIRED`, `REQUEST_MORE_INFORMATION`.
* **Milestones:** `first_symptom`, `health_crisis`, `severe_episode`, `near_death`, `full_recovery`.
* **Candidate Metrics:**
  * **Decision Accuracy:** Overall rate of correct trigger decisions.
  * **False Deterioration Rate:** Rate at which healthy/stable plants trigger advice:
    $$\text{FDR} = \frac{\text{False CARE\_ADVICE\_REQUIRED on Stable/Improving Days}}{\text{Total Stable/Improving Days}}$$
  * **Milestone Detection Precision & Recall:** Exact calendar-day accuracy for detected milestones.
* > [!IMPORTANT]
  > **TODO (Human Action Required — Item H5):** Real-world multi-day plant sequences under varying lighting/camera drift to be populated in `evaluation/datasets/plant_health_tracking/tracking_sequences.json`. (Initial baseline executes on the 6 scenario datasets).

### Scope E: End-to-End System
* **Function Under Test:**
  * `orchestrator.worker.execute_run` across pipeline stages: `capture` $\to$ `assessment` $\to$ `advice` $\to$ `companion`.
* **Benchmark Scenarios:**
  1. `no_change`: Multi-day healthy baseline ($\to$ `NO_ACTION`, template companion).
  2. `new_symptom`: Healthy $\to$ leaf yellowing ($\to$ `CARE_ADVICE_REQUIRED`, advice generated).
  3. `severity_increase`: Mild $\to$ severe symptom escalation ($\to$ `CARE_ADVICE_REQUIRED`, crisis dialogue).
  4. `improvement`: Unhealthy $\to$ recovery ($\to$ `NO_ACTION`, encouragement dialogue).
  5. `health_status_change`: Healthy $\to$ unhealthy degradation.
  6. `milestone_lifecycle`: Full progression through crisis, severe episode, and recovery.
* **Candidate Metrics:**
  * **Scenario Success Rate:**
    $$\text{SSR} = \frac{\text{Passed Scenarios}}{\text{Total Evaluated Scenarios}} \times 100\%$$
    (A scenario passes only if 100% of its mandatory criteria pass).
  * **FE Envelope Contract Compliance Rate:** Adherence to frontend structure matching `poc-ai-agent`.
  * **Stage Latency Profile:** Median, p90, and p95 latency per stage and end-to-end.
* > [!IMPORTANT]
  > **TODO (Human Action Required — Item H6):** Define production latency SLAs (e.g. median $< 2.5$s, p95 $< 6.0$s) in `evaluation/config/default.json` once deployment hardware is benchmarked.

---

## 5. Command-Line Interface (CLI)

```bash
# Run all configured evaluation scopes
uv run python -m evaluation.scripts.cli run

# Run a specific scope
uv run python -m evaluation.scripts.cli run --scope image_preprocessing
uv run python -m evaluation.scripts.cli run --scope vlm
uv run python -m evaluation.scripts.cli run --scope llm
uv run python -m evaluation.scripts.cli run --scope plant_health_tracking
uv run python -m evaluation.scripts.cli run --scope end_to_end

# Enable optional opt-in LLM judge (disabled by default)
uv run python -m evaluation.scripts.cli run --scope llm --enable-judge

# Validate evaluation manifests and schemas
uv run python -m evaluation.scripts.cli validate

# Safe cleanup: dry-run inspection (default)
uv run python -m evaluation.scripts.cli clean --dry-run

# Safe cleanup: confirmed execution
uv run python -m evaluation.scripts.cli clean --yes
```

### Exit Code Semantics
* `0`: Success — all executed evaluations passed their assertions. (Scopes skipped due to missing weights/data do not cause exit code 1).
* `1`: Failure — at least one evaluated metric fell below its failure threshold or a mandatory scenario criterion failed.
* `2`: Setup / Configuration Error — invalid dataset JSON, unknown scope, or invalid CLI parameters.

---

## 6. Human Action & Labeling Backlog (TODOs)

The following table explicitly tracks every item that requires human judgment, domain knowledge, or real-world data collection. The automated evaluation harness is architected to operate with test fixtures or skip missing datasets until these are populated.

| ID | Domain / Scope | Target File Location | Who Needs to Provide It | What Needs to be Done | Current System Behavior Until Filled |
|---|---|---|---|---|---|
| **H1** | Image Preprocessing | `evaluation/datasets/image_preprocessing/manifest.json` | Hardware / QA Engineer | Collect and label real webcam/device photos across lighting extremes (underexposed $<40$, overexposed $>220$) and blur conditions. | Synthetic images from `capture_fakes` are used for baseline verification. |
| **H2** | VLM Symptom Analysis | `evaluation/datasets/vlm/manifest_template.json` $\to$ `manifest.json` | Botanist / Plant Specialist | Label real plant photo pairs with independent ground-truth symptoms (`leaf_yellowing`, `drooping`, etc.), severities, and probe answers. | Scope reports `SKIPPED (reason: pending real labeled dataset)` without failing test suite. |
| **H3** | LLM Advice Ground Truth | `evaluation/datasets/llm/advice_cases.json` | Plant Care Specialist | Review golden reference advice texts, prohibited medical/chemical claims, and ideal action orderings for diagnostic cases. | Deterministic schema and 3NF action grounding checks run against canned golden cases. |
| **H4** | LLM Judge Provider | `evaluation/config/default.json` & `.env` | Team Lead / Architect | Select judge LLM model (e.g., `gpt-4o`, `claude-3-5-sonnet`, or local `llama3.3`) and configure API credentials. | Judge evaluation is disabled by default; only deterministic metrics execute unless `--enable-judge` is passed. |
| **H5** | Multi-Day Plant Sequences | `evaluation/datasets/plant_health_tracking/tracking_sequences.json` | Plant Lab / QA | Add real multi-day camera photos tracking physical plants through wilting, recovery, and steady growth. | Evaluates against the 6 verified multi-day scenario datasets in `fixtures/`. |
| **H6** | Production Latency SLAs | `evaluation/config/default.json` | DevOps / Infra Team | Set production latency threshold goals (median and p95 ms) based on target server compute. | Latency percentiles are measured and reported for information without enforcing hard gating thresholds. |

---

## 7. How Humans Validate and Add Data Later

When filling in any of the above TODO items:

1. **Step 1: Check Manifest Schemas**
   Review `evaluation/datasets/README.md` and the relevant schema in `evaluation/common/loaders.py`.
2. **Step 2: Add Images & JSON Entries**
   Place image files in `evaluation/datasets/<scope>/samples/` and update `manifest.json`.
3. **Step 3: Validate Schemas Automatically**
   Run the CLI validation command:
   ```bash
   uv run python -m evaluation.scripts.cli validate
   ```
   This performs structural and schema validation on all JSON manifests without running model inferences.
4. **Step 4: Execute Scope Evaluation**
   Run the specific evaluation scope:
   ```bash
   uv run python -m evaluation.scripts.cli run --scope <scope_name>
   ```
   Check `evaluation/reports/latest/summary.md` to inspect the resulting metrics.

---

## 8. Safe Cleanup Policy

1. **Root Lockdown:** The target cleanup directory is strictly resolved to `<workspace>/evaluation/reports/`.
2. **Path Sanitization:** Any relative or symlinked path attempting to escape this root directory raises an immediate `ValueError` and terminates execution.
3. **Protected Files:** Files matching `.gitkeep`, `README.md`, or any file outside `reports/` are excluded from deletion.
4. **Mandatory Confirmation:** No files are deleted unless the `--yes` flag is explicitly provided.

---

## 9. Testing Strategy for Evaluation Tooling

All tooling will be tested under `tests/test_evaluation_suite.py`:
1. `test_manifest_schema_validation`: Validates proper error reporting on malformed JSON.
2. `test_metric_calculations`: Tests precision, recall, and macro-F1 on known edge cases (e.g. division by zero, empty sets).
3. `test_missing_scope_skip_behavior`: Confirms that unconfigured VLM or judge scopes cleanly mark `SKIPPED` without throwing unexpected exceptions.
4. `test_cli_dispatch_and_exit_codes`: Tests argument parsing and proper exit code delivery.
5. `test_cleanup_sandbox_safety`: Verifies path rejection for paths outside `evaluation/reports/`.
6. `test_smoke_evaluation_execution`: Executes a fast mock run of all scopes in $<5$ seconds.

---

## 10. Definition of Done Checklist

- [ ] Top-level `evaluation/` directory created with comprehensive `README.md`.
- [ ] Datasets and manifest templates provided for all 5 scopes.
- [ ] Human Action Backlog (TODOs H1–H6) explicitly documented and referenced.
- [ ] All 5 scope runners (`image_preprocessing`, `vlm`, `llm`, `plant_health_tracking`, `end_to_end`) implemented.
- [ ] Safe cleanup utility implemented with strict path allowlisting and dry-run default.
- [ ] CLI supports running all scopes, running individual scopes, and validating datasets.
- [ ] Unit and smoke tests in `tests/test_evaluation_suite.py` pass with `uv run pytest`.
- [ ] Output reports in `evaluation/reports/<run-id>/` generate valid `summary.json`, `summary.md`, and `.jsonl` files.
