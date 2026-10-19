# Pet-Plant Performance Evaluation Report — `run_2026`

- **Run ID:** `run_20261018_085332_a032c5`
- **Timestamp:** `2026-10-18T10:16:46.545148+00:00`
- **Duration:** `4993.71s`
- **Overall Status:** **FAIL**
- **Git Commit:** `e472fae`
- **Python Version:** `3.13.7`

## Active Models & Environment

| Role | Model / Setting |
|---|---|
| **Vlm Model** | `models/internvl3_5-2b (local)` |
| **Llm Model** | `llama3.2:latest (ollama)` |
| **Embedding Model** | `nomic-embed-text:latest (ollama)` |
| **Execution Mode** | `in_memory` |

## Scope Summary Table

| Scope | Status | Cases Passed | Duration | Key Metrics | Notes |
|---|---|---|---|---|---|
| `vlm` | **FAIL** | 258/505 | 4985.87s | health_status_accuracy=51.09%, health_status_f1=67.28%, symptoms_micro_f1=20.05%, symptoms_macro_f1=10.86% | - |
| `llm` | **PASS** | 5/5 | 0.93s | advice_schema_conformance=100.00%, mean_semantic_similarity=88.83%, mean_response_difference=11.17%, mean_action_alignment=100.00%, mean_lexical_similarity=8.36% | - |
| `end_to_end` | **PASS** | 6/6 | 6.85s | scenario_success_rate=100.00%, fe_envelope_compliance_rate=100.00%, median_pipeline_latency_ms=914.50ms | - |

## Aggregation Scorecard

| Scope | Metric | Value | Threshold | Status |
|---|---|---|---|---|
| `vlm` | Health Status Accuracy | 51.09% | >= 75.00% | **FAIL** |
|  | Health Status F1 | 67.28% | >= 75.00% | **FAIL** |
|  | Symptoms Micro F1 | 20.05% | >= 60.00% | **FAIL** |
|  | Symptoms Macro F1 | 10.86% | >= 50.00% | **FAIL** |
| | **Cases Passed** | 258/505 (51.1%) | — | **FAIL** |
| | | | | |
| `llm` | Advice Schema Conformance | 100.00% | >= 100.00% | **PASS** |
|  | Mean Semantic Similarity | 88.83% | >= 70.00% | **PASS** |
|  | Mean Response Difference | 11.17% | <= 30.00% | **PASS** |
|  | Mean Action Alignment | 100.00% | >= 80.00% | **PASS** |
|  | Mean Lexical Similarity | 8.36% | - | **PASS** |
| | **Cases Passed** | 5/5 (100.0%) | — | **PASS** |
| | | | | |
| `end_to_end` | Scenario Success Rate | 100.00% | >= 100.00% | **PASS** |
|  | Fe Envelope Compliance Rate | 100.00% | >= 100.00% | **PASS** |
|  | Median Pipeline Latency Ms | 914.50ms | <= 2500ms | **PASS** |
| | **Cases Passed** | 6/6 (100.0%) | — | **PASS** |
| | | | | |

## Detailed Scope Metrics

### Scope: `vlm` (FAIL)
| Metric | Value | Threshold | Status | Note |
|---|---|---|---|---|
| `health_status_accuracy` | 51.09% | >= 75.00% | **FAIL** | Overall accuracy in predicting healthy vs unhealthy plants. |
| `health_status_f1` | 67.28% | >= 75.00% | **FAIL** | Harmonic mean of precision and recall for plant condition assessment. |
| `symptoms_micro_f1` | 20.05% | >= 60.00% | **FAIL** | Global Micro-F1 across multi-label botanical symptom detections. |
| `symptoms_macro_f1` | 10.86% | >= 50.00% | **FAIL** | Unweighted Macro-F1 across all standardized symptom tags. |

#### Health Status Multi-Class Confusion Matrix

| Expected \ Actual | `healthy` | `unhealthy` | Total |
|---|---|---|---|
| **`healthy`** | 4 | 246 | **250** |
| **`unhealthy`** | 1 | 254 | **255** |
| **Total** | **5** | **500** | **505** |

#### `vlm` Endpoints / Stages Called

| Method | Path / Stage | Calls | Source |
|---|---|---|---|
| `—` | `vlm.final_dataset.load_final_dataset` | 1 | in-memory |
| `—` | `vlm.predictor.FinalDatasetPredictor` | 505 | in-memory |
| `—` | `vlm.metrics.evaluate_final_dataset_metrics` | 1 | in-memory |

### Scope: `llm` (PASS)
| Metric | Value | Threshold | Status | Note |
|---|---|---|---|---|
| `advice_schema_conformance` | 100.00% | >= 100.00% | **PASS** | 100% adherence to 3NF care plan structure and action grounding. |
| `mean_semantic_similarity` | 88.83% | >= 70.00% | **PASS** | Mean semantic similarity between expected and actual assessment responses. |
| `mean_response_difference` | 11.17% | <= 30.00% | **PASS** | Mean difference percentage between expected and actual response via (100 - (similarity) * 100). |
| `mean_action_alignment` | 100.00% | >= 80.00% | **PASS** | Mean overlap percentage of recommended care actions against expected actions. |
| `mean_lexical_similarity` | 8.36% | - | **PASS** | Informational: Mean character and word SequenceMatcher alignment. |

#### `llm` Response Similarity & Difference Breakdown

| Case ID | Expected Assessment | Actual Assessment | Similarity (%) | Difference (%) | Action Overlap (%) | Status |
|---|---|---|---|---|---|---|
| `CASE-ADVICE-001` | Lower leaves show solid bright yellow discoloration likely related to chronic overwatering. The potting soil remains constantly soggy for extended periods, cutting off oxygen to roots. Upper canopy remains healthy, suggesting the issue is localized to the root zone. | Lower leaves exhibit solid yellow discoloration, characteristic of prolonged soil moisture preventing root oxygen uptake. The upper canopy appears unaffected. Recommend withholding water until topsoil is dry and inspecting root health. | 92.09% | 7.91% | 100.00% | **PASS** |
| `CASE-ADVICE-002` | The entire canopy droops significantly with stems losing structural rigidity. The potting soil has become completely bone dry throughout the entire root zone, causing loss of turgor pressure. Immediate deep watering is critical. | Plant shows dramatic wilting with all leaves drooping downward and stems appearing shriveled due to complete root zone dryness. Turgor pressure has been lost throughout. Immediate thorough watering through the drainage holes is required. | 87.36% | 12.64% | 100.00% | **PASS** |
| `CASE-ADVICE-003` | Leaf margins and tips show dry, brittle browning with characteristic yellow transition zone. The ambient indoor air is excessively dry, often due to active indoor heating or air conditioning. Interior leaf tissue remains green, indicating the damage is humidity-related. | Brown crispy edges observed along leaf margins with a narrow yellow band separating damaged tissue from the healthy green center. Symptoms consistent with dry indoor air conditions. Increasing ambient humidity and moving the plant away from air conditioning is recommended. | 90.53% | 9.47% | 100.00% | **PASS** |
| `CASE-ADVICE-004` | Upper leaves facing the window show bleached, pale yellowish-green coloration with dry papery brown scorch marks. Direct harsh afternoon sunlight is physically burning the delicate leaf tissue. Plant should be relocated to bright indirect light. | Light-facing foliage appears washed out and faded with brown papery marks on the most exposed leaves. Damage pattern indicates excessive direct sunlight burning the leaf tissue. Moving the plant to a spot with diffused light will prevent further damage. | 88.29% | 11.71% | 100.00% | **PASS** |
| `CASE-ADVICE-005` | Selected leaves show soft mushy base tissue changing from stiff green to dark brownish-yellow. This indicates the root system is decaying from persistent moisture. Immediate removal of affected tissue and repotting in dry well-draining mix is critical to prevent spreading. | Base of affected leaves has become soft and water-soaked with dark brownish discoloration, indicating fungal rot from overwatering. The root system likely has similar decay. Removing damaged tissue and repotting in fast-draining soil is essential. | 85.89% | 14.11% | 100.00% | **PASS** |

> *Note: Difference (%) is calculated using the formula `(100 - (similarity) * 100)` where similarity is normalized in [0.0, 1.0].*

#### `llm` Endpoints / Stages Called

| Method | Path / Stage | Calls | Source |
|---|---|---|---|
| `—` | `advice.service  (care plan generation)` | 5 | in-memory |
| `—` | `evaluation.common.metrics.calculate_text_similarity` | 5 | in-memory |
| `—` | `evaluation.common.metrics.calculate_jaccard  (action alignment)` | 5 | in-memory |

### Scope: `end_to_end` (PASS)
| Metric | Value | Threshold | Status | Note |
|---|---|---|---|---|
| `scenario_success_rate` | 100.00% | >= 100.00% | **PASS** | All mandatory criteria must pass for every scenario. |
| `fe_envelope_compliance_rate` | 100.00% | >= 100.00% | **PASS** | Adherence to poc-ai-agent Frontend Response Envelope contract. |
| `median_pipeline_latency_ms` | 914.50ms | <= 2500ms | **PASS** | Median pipeline run latency. |

#### `end_to_end` Endpoints / Stages Called

| Method | Path / Stage | Calls | Source |
|---|---|---|---|
| `—` | `orchestrator.worker.execute_run` | 6 | in-memory |
| `—` | `orchestrator.stages.claim_frame  (capture stage)` | 6 | in-memory |
| `—` | `orchestrator.stages.assess_frames  (assessment stage)` | 6 | in-memory |
| `—` | `advice  (LLM care-plan stage)` | 6 | in-memory |
| `—` | `companion  (companion message stage)` | 6 | in-memory |
