# Pet-Plant Performance Evaluation Report — `run_2026`

- **Run ID:** `run_20261017_165533_fe59e7`
- **Timestamp:** `2026-10-17T16:55:36.684561+00:00`
- **Duration:** `2.87s`
- **Overall Status:** **PASS**
- **Git Commit:** `e630077`
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
| `vlm` | **PASS** | 33/33 | 1.47s | mean_semantic_similarity=97.16%, mean_response_difference=2.84%, probe_answer_accuracy=100.00%, structured_f1_score=100.00%, structured_precision=100.00, structured_recall=100.00, batch_photo_success_rate=100.00%, mean_lexical_similarity=82.60% | - |
| `llm` | **PASS** | 5/5 | 0.11s | advice_schema_conformance=100.00%, mean_semantic_similarity=88.83%, mean_response_difference=11.17%, mean_action_alignment=100.00%, mean_lexical_similarity=8.36% | - |
| `end_to_end` | **PASS** | 6/6 | 1.29s | scenario_success_rate=100.00%, fe_envelope_compliance_rate=100.00%, median_pipeline_latency_ms=36.39ms | - |

## Aggregation Scorecard

| Scope | Metric | Value | Threshold | Status |
|---|---|---|---|---|
| `vlm` | Mean Semantic Similarity | 97.16% | >= 70.00% | **PASS** |
|  | Mean Response Difference | 2.84% | <= 30.00% | **PASS** |
|  | Probe Answer Accuracy | 100.00% | >= 100.00% | **PASS** |
|  | Structured F1 Score | 100.00% | >= 80.00% | **PASS** |
|  | Structured Precision | 100.00 | 80.0 | **PASS** |
|  | Structured Recall | 100.00 | 80.0 | **PASS** |
|  | Batch Photo Success Rate | 100.00% | >= 50.00% | **PASS** |
|  | Mean Lexical Similarity | 82.60% | - | **PASS** |
| | **Cases Passed** | 33/33 (100.0%) | — | **PASS** |
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
|  | Median Pipeline Latency Ms | 36.39ms | <= 2500ms | **PASS** |
| | **Cases Passed** | 6/6 (100.0%) | — | **PASS** |
| | | | | |

## Detailed Scope Metrics

### Scope: `vlm` (PASS)
| Metric | Value | Threshold | Status | Note |
|---|---|---|---|---|
| `mean_semantic_similarity` | 97.16% | >= 70.00% | **PASS** | Mean semantic similarity between expected and actual VLM assessment responses. |
| `mean_response_difference` | 2.84% | <= 30.00% | **PASS** | Mean difference percentage via (100 - (similarity) * 100). |
| `probe_answer_accuracy` | 100.00% | >= 100.00% | **PASS** | All VLM probe answers (yes/no) must match expected ground truth. |
| `structured_f1_score` | 100.00% | >= 80.00% | **PASS** | Harmonic mean of precision and recall on structured JSON symptom/probe findings. |
| `structured_precision` | 100.00 | 80.0 | **PASS** | Proportion of detected symptoms/probes that were true positives. |
| `structured_recall` | 100.00 | 80.0 | **PASS** | Proportion of expected symptoms/probes successfully detected. |
| `batch_photo_success_rate` | 100.00% | >= 50.00% | **PASS** | Batch photo criteria pass rate: 29/29 photos passed criteria. |
| `mean_lexical_similarity` | 82.60% | - | **PASS** | Informational: Mean character and word SequenceMatcher alignment. |

#### `vlm` Response Similarity & Difference Breakdown

| Case ID | Expected Assessment | Actual Assessment | Similarity (%) | Difference (%) | Action Overlap (%) | Status |
|---|---|---|---|---|---|---|
| `VLM-CASE-001` | Multiple lower leaves exhibit solid bright yellow discoloration simultaneously, characteristic of prolonged soil moisture. Upper canopy remains healthy green. Pattern is consistent with overwatering stress affecting the oldest foliage first. | Lower leaves near the soil line show uniform yellowing, suggesting the root zone has been consistently wet. The newer growth at the top appears unaffected, indicating early-stage overwatering symptoms. | 87.51% | 12.49% | - | **PASS** |
| `VLM-CASE-002` | The entire canopy droops significantly with stems losing structural rigidity. Leaves hang limply rather than standing outward. This is consistent with severe dehydration where the root zone has become completely dry. | Plant shows dramatic wilting with all leaves drooping downward over the pot rim. Foliage lacks turgor pressure. The condition indicates critical water deficit throughout the root zone. | 78.24% | 21.76% | - | **PASS** |
| `VLM-CASE-003` | Leaf margins and tips show dry, brittle browning with characteristic yellow transition zone. The interior leaf tissue remains green, indicating the damage is humidity-related rather than systemic. Pattern consistent with low ambient humidity stress. | Brown crispy edges observed along leaf margins, particularly on older leaves. A narrow yellow band separates damaged edges from the green center. Consistent with dry air conditions typical of indoor heating. | 82.20% | 17.80% | - | **PASS** |
| `VLM-CASE-004` | All leaves appear uniformly deep green with no discoloration. Foliage stands upright with good turgor. No visible signs of overwatering or nutrient deficiency detected. Plant appears in excellent health. | The plant displays consistent dark green coloring across all foliage. Leaves are erect and well-hydrated. No yellowing, browning, or wilting symptoms are present. Overall health status is good. | 90.54% | 9.46% | - | **PASS** |
| `VLM-CASE-005` | Upper leaves facing the window show bleached, pale yellowish-green coloration with distinct dry brown scorch patches. Lower and shaded leaves remain their normal green. Damage pattern indicates direct sunlight exposure burning the foliage. | Light-facing foliage appears washed out and faded compared to shaded leaves. Brown papery marks visible on the most exposed leaves. Symptoms are consistent with sun scorch from excessive direct light exposure. | 87.25% | 12.75% | - | **PASS** |
| `VLM-CASE-006` | The canopy is deep glossy green and the leaf stems stand firm before the blades arch outward. One leaf tip on the right is slightly pale, but the lower leaves are not turning solid yellow together. This is a healthy Peace lily in bright indirect window light. | The canopy is deep glossy green and the leaf stems stand firm before the blades arch outward. One right-side leaf tip is slightly pale, while the lower leaves are not turning solid yellow together. The Peace lily looks healthy in bright indirect window light. | 98.98% | 1.02% | - | **PASS** |
| `VLM-CASE-007` | Leaves are a uniform deep glossy green from the soil line to the top of the canopy. Stems hold the foliage up and the blades arch outward, which is normal for a Peace lily. No widespread yellowing of lower leaves is visible. | Leaves show a uniform deep glossy green from the soil line to the top of the canopy. Stems hold the foliage up and the blades arch outward, which is normal for a Peace lily. Widespread yellowing of lower leaves is not visible. | 99.34% | 0.66% | - | **PASS** |
| `VLM-CASE-008` | From above, the plant forms a full dark green canopy. Leaf stems rise from the crown and the blades stay glossy. There is no solid yellowing across the lower leaves. | From above, the plant forms a full dark green canopy. Leaf stems rise from the crown and the blades stay glossy. Solid yellowing across the lower leaves is absent. | 99.36% | 0.64% | - | **PASS** |
| `VLM-CASE-009` | The top-down view shows even glossy dark green leaves with no pale or yellow blades. The crown is full and the foliage is not collapsing toward the pot. Lower leaves match the dark green of the upper canopy. | The top-down view shows even glossy dark green leaves without pale or yellow blades. The crown is full and the foliage is not collapsing toward the pot. Lower leaves match the dark green of the upper canopy. | 99.92% | 0.08% | - | **PASS** |
| `VLM-CASE-010` | The plant is lush, with firm stems and glossy dark green leaf blades. The outward arch of mature leaves is the normal Peace lily shape, not wilt. No group of lower leaves is solid yellow. | The plant is lush, with firm stems and glossy dark green leaf blades. The outward arch of mature leaves is the normal Peace lily shape rather than wilt. No group of lower leaves is solid yellow. | 99.92% | 0.08% | - | **PASS** |
| `VLM-CASE-011` | The silhouette is bushy and the leaves are a consistent dark green. Stems remain supportive and the soil line shows no cluster of yellow lower leaves. The plant looks hydrated and healthy. | The silhouette is bushy and the leaves are a consistent dark green. Stems remain supportive and the soil line shows no cluster of yellow lower leaves. The plant looks hydrated and in good health. | 99.56% | 0.44% | - | **PASS** |
| `VLM-CASE-012` | Several leaves hang lower than the plant's usual firm arch, and one leaf in the crown is yellow. The canopy has not collapsed over the pot rim and most blades are still dark green, so this is mild limpness rather than severe wilting. | Several leaves hang lower than the plant's usual firm arch, and one crown leaf is yellow. The canopy has not collapsed over the pot rim and most blades are still dark green, so this is mild limpness rather than severe wilting. | 99.81% | 0.19% | - | **PASS** |
| `VLM-CASE-013` | The outer leaves hang and yellow tissue shows in the center of the crown. Most of the canopy is still green and the stems have not folded down over the rim. The change is mild limpness with a single yellowing leaf, not severe wilting. | The outer leaves hang and yellow tissue shows in the center of the crown. Most of the canopy is still green and the stems have not folded down over the rim. This is mild limpness with a single yellowing leaf, not severe wilting. | 97.58% | 2.42% | - | **PASS** |
| `VLM-CASE-014` | Leaves lean and hang more than on the firm days, and one yellow leaf sits in the crown beside the tag. The rest of the foliage is dark green and the whole canopy is not draped over the pot rim. This is early limpness, not severe wilting. | Leaves lean and hang more than on the firm days, and one yellow leaf sits in the crown beside the tag. The rest of the foliage is dark green and the whole canopy is not draped over the pot rim. This reads as early limpness, not severe wilting. | 99.31% | 0.69% | - | **PASS** |
| `VLM-CASE-015` | The next day the stems are upright again and the leaves are glossy dark green, with water droplets on the foliage. Lower leaves match the upper canopy and are not solid yellow. The plant looks recovered and healthy. | The next day the stems are upright again and the leaves are glossy dark green, with water droplets on the foliage. Lower leaves match the upper canopy and are not solid yellow. The plant looks recovered and in good health. | 99.74% | 0.26% | - | **PASS** |
| `VLM-CASE-016` | Foliage is glossy and dark green, with a gentle outward arch of the mature blades. Stems are supportive and there is no simultaneous yellowing of the lower leaves. The plant appears healthy. | Foliage is glossy and dark green, with a gentle outward arch of the mature blades. Stems are supportive and there is no simultaneous yellowing of the lower leaves. The plant appears in good health. | 99.01% | 0.99% | - | **PASS** |
| `VLM-CASE-017` | The canopy is full and the leaves hold a deep green color with firm stems. The natural arch does not include limp stems at the soil. Widespread yellowing of lower leaves is not present. | The canopy is full and the leaves hold a deep green color with firm stems. The natural arch does not include limp stems at the soil. Widespread yellowing of lower leaves is absent. | 99.85% | 0.15% | - | **PASS** |
| `VLM-CASE-018` | Leaves are dark, glossy, and evenly green. Stems stand up from the pot and only the blades curve outward. Lower leaves are the same deep green as the upper leaves, with no widespread yellowing. | Leaves are dark, glossy, and evenly green. Stems stand up from the pot and only the blades curve outward. Lower leaves are the same deep green as the upper leaves, without widespread yellowing. | 99.93% | 0.07% | - | **PASS** |
| `VLM-CASE-019` | The canopy is open and the leaves are a rich green with shiny surfaces. Petioles hold the foliage out from the crown. There is no solid yellow discoloration on the lower leaves. | The canopy is open and the leaves are a rich green with shiny surfaces. Petioles hold the foliage out from the crown. Solid yellow discoloration on the lower leaves is not present. | 99.11% | 0.89% | - | **PASS** |
| `VLM-CASE-020` | Under indoor light the leaves remain dark green and the stems stay firm. The slight shadow does not hide any yellow lower leaves. The plant looks healthy. | Under indoor light the leaves remain dark green and the stems stay firm. The slight shadow does not hide any yellow lower leaves. The plant looks in good health. | 99.37% | 0.63% | - | **PASS** |
| `VLM-CASE-021` | The afternoon frame shows a full canopy of dark green leaves with firm stems. Color is even from the lower blades to the top. Widespread yellowing of lower leaves is not visible. | The afternoon frame shows a full canopy of dark green leaves with firm stems. Color is even from the lower blades to the top. Widespread yellowing of lower leaves is absent. | 99.41% | 0.59% | - | **PASS** |
| `VLM-CASE-022` | Leaves are glossy and deep green, held out on firm stems. The lower foliage matches the upper leaves in color. There is no widespread yellowing. | Leaves are glossy and deep green, held out on firm stems. The lower foliage matches the upper leaves in color. Widespread yellowing is not present. | 99.15% | 0.85% | - | **PASS** |
| `VLM-CASE-023` | The plant has an even dark green color and a normal arching habit. Stems are firm near the soil. Lower leaves are not turning yellow together. | The plant has an even dark green color and a normal arching habit. Stems are firm near the soil. Lower leaves are not turning yellow at the same time. | 99.70% | 0.30% | - | **PASS** |
| `VLM-CASE-024` | The foliage is dark green and firm. One leaf has a small notch on the edge, which looks like a tear rather than yellowing or wilt. Lower leaves are not solid yellow. | The foliage is dark green and firm. One leaf has a small notch on the edge, which looks like a tear rather than yellowing or wilt. Lower leaves are not a solid yellow. | 99.96% | 0.04% | - | **PASS** |
| `VLM-CASE-025` | Leaves are uniformly dark green and held on firm stems. A small nick on one margin is mechanical damage, not chlorosis. There is no widespread yellowing of the lower leaves. | Leaves are uniformly dark green and held on firm stems. A small nick on one margin is mechanical damage, not chlorosis. Widespread yellowing of the lower leaves is not visible. | 99.35% | 0.65% | - | **PASS** |
| `VLM-CASE-026` | A new spear leaf is unfurling in the crown and the mature leaves are dark green. Some blades are folded as they expand, while the stems still hold the plant up. Lower leaves are not yellowing together. | A new spear leaf is unfurling in the crown and the mature leaves are dark green. Some blades are folded as they expand, while the stems still hold the plant up. Lower leaves are not yellowing at the same time. | 99.71% | 0.29% | - | **PASS** |
| `VLM-CASE-027` | The latest frame shows a compact dark green Peace lily with firm stems and glossy blades. Color is even through the lower leaves. No widespread yellowing is visible. | The latest frame shows a compact dark green Peace lily with firm stems and glossy blades. Color is even through the lower leaves. Widespread yellowing is not visible. | 99.19% | 0.81% | - | **PASS** |
| `VLM-CASE-028` | Many leaves have faded to yellow-green at the same time, including older outer leaves, while some centers remain greener. This is widespread yellowing rather than one spent bottom leaf. The plant is stressed but not yet collapsed. | Many leaves have faded to yellow-green at the same time, including older outer leaves, while some centers remain greener. This is widespread yellowing rather than one spent bottom leaf. The plant is stressed but has not collapsed. | 99.90% | 0.10% | - | **PASS** |
| `VLM-CASE-029` | Most leaves hang limp and have turned yellow to tan, with only a little green left in the crown. Stems have lost firmness and the soil surface looks dry. This is severe wilting from water deficit. | Most leaves hang limp and have turned yellow to tan, with only a little green left in the crown. Stems have lost firmness and the soil surface looks dry. This matches severe wilting from water deficit. | 99.32% | 0.68% | - | **PASS** |
| `VLM-CASE-030` | Leaves hang and most of each blade is dead brown tissue on a yellow background. Stems no longer hold the canopy up. This is severe wilting with extensive leaf death, consistent with prolonged dryness. | Leaves hang and most of each blade is dead brown tissue on a yellow background. Stems no longer hold the canopy up. This is severe wilting with extensive leaf death, consistent with prolonged dry soil. | 98.46% | 1.54% | - | **PASS** |
| `VLM-CASE-031` | The leaves are brown, curled, and collapsed, and the soil is cracked and shrunk away from the pot wall. Almost no green tissue remains. This is severe desiccation from water deficit. | The leaves are brown, curled, and collapsed, and the soil is cracked and shrunk away from the pot wall. Almost no green tissue remains. This is severe drying from water deficit. | 96.59% | 3.41% | - | **PASS** |
| `VLM-CASE-032` | Every visible leaf is brown, dry, and crumpled, with no remaining green blade. The canopy has fully collapsed. This is a dead plant after severe water deficit. | Every visible leaf is brown, dry, and crumpled, with no remaining green blade. The canopy has fully collapsed. This is a dead plant after severe lack of water. | 99.20% | 0.80% | - | **PASS** |
| `VLM-CASE-033` | This image is a six-panel sequence of one Peace lily. It starts with widespread yellowing, then brown collapse, and ends as dry brown leaves over cracked soil. The series shows severe wilting from water deficit through to plant death. | This image is a six-panel sequence of one Peace lily. It starts with widespread yellowing, then brown collapse, and ends as dry brown leaves over cracked soil. The series shows severe wilting from water deficit through to death of the plant. | 99.77% | 0.23% | - | **PASS** |

> *Note: Difference (%) is calculated using the formula `(100 - (similarity) * 100)` where similarity is normalized in [0.0, 1.0].*

#### `vlm` Endpoints / Stages Called

| Method | Path / Stage | Calls | Source |
|---|---|---|---|
| `—` | `assessment.vlm  (plant symptom analysis)` | 33 | in-memory |
| `—` | `vlm.metrics.evaluate_probe_findings` | 33 | in-memory |
| `—` | `vlm.metrics.evaluate_symptoms_classification` | 33 | in-memory |
| `—` | `evaluation.common.metrics.calculate_text_similarity` | 33 | in-memory |
| `—` | `vlm.run.evaluate_batch_photos  (batch photo engine)` | 1 | in-memory |

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
| `median_pipeline_latency_ms` | 36.39ms | <= 2500ms | **PASS** | Median pipeline run latency. |

#### `end_to_end` Endpoints / Stages Called

| Method | Path / Stage | Calls | Source |
|---|---|---|---|
| `—` | `orchestrator.worker.execute_run` | 6 | in-memory |
| `—` | `orchestrator.stages.claim_frame  (capture stage)` | 6 | in-memory |
| `—` | `orchestrator.stages.assess_frames  (assessment stage)` | 6 | in-memory |
| `—` | `advice  (LLM care-plan stage)` | 6 | in-memory |
| `—` | `companion  (companion message stage)` | 6 | in-memory |
