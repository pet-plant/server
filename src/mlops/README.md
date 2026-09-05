# `mlops` — Evaluation & MLOps (context 7)

AI quality assurance: ClearML is the authoring / experimentation / comparison
store for the prompts and configs the AI contexts run on; this context evaluates
candidates, gates them, and ships approved ones to their consuming context.

> Status: **template scaffolding only.** Every function body is
> `raise NotImplementedError` / every endpoint returns `501`. The concrete logic
> and the runtime hand-off mechanism are not decided yet.

## Managed artifacts (bundle kinds)

Each is versioned as a **bundle** — a self-contained payload (prompt text and/or
structured config) plus metadata. One `BundleSpec` per kind in `bundles/`.

| `BundleKind` | Payload | Consumer |
|---|---|---|
| `assessment_vlm_prompt` | VLM probe prompt template + decoding | `assessment` |
| `advice_llm_prompt` | advice LLM prompt template(s) + decoding | `advice` |
| `advice_agent` | agent structure as data (nodes / tools / edges / model) | `advice` |
| `knowledge_probe_prompt` | probe-generation prompt + output contract | `knowledge` |

Add a kind: new `BundleKind` member → new `bundles/<kind>.py` with its `*Spec` →
register in `bundles.BUNDLE_SPECS` → add `settings.CLEARML_SUBPROJECT` entry.

## Flow

```
author in ClearML ──▶ pull candidate ──▶ evaluate vs frozen eval set ──▶ compare
   (tracking/)         (tracking/         (evaluation/runner +            (evaluation/
                        bundle_store)      evaluation/metrics)             compare)
                                                                             │
                                                            promotion gates  ▼
                                                            (promotion/gates)
                                                                             │
                                                    freeze + hand off  ──────▼
                                                    (promotion/ship)   shipped bundle
                                                                             │
                              consuming context reads it ◀── mlops.interface.get_active_bundle
```

Scores and comparisons are mirrored into ClearML (`tracking/experiment.py`) so
the ClearML compare view is the human-facing "検証と比較" surface.

## Layout

| Path | Responsibility |
|---|---|
| `bundles/` | one module per managed artifact — payload model + `BundleSpec` (validate / render / fingerprint) |
| `tracking/` | **the only place `import clearml` appears** — session, candidate push/pull, experiment logging |
| `evaluation/` | frozen eval sets, run a candidate, score, champion/challenger compare |
| `promotion/` | promotion gates + `ship.py` (freeze + hand-off seam) |
| `models/` | `mlops` Postgres schema: `bundle_version`, `eval_run` / `eval_result`, `promotion_record` |
| `jobs/` | worker entrypoints (`run_evaluation`, `sync_bundles`), dispatched from `main_worker.py` |
| `api.py` | `/mlops` router — list / trigger eval / inspect / promote |
| `interface.py` | in-process `get_active_bundle(kind, target=…)` for other contexts |
| `service.py` | persistence / read queries over the `mlops` schema |
| `db.py` | schema wiring (mirrors `knowledge/db.py`) |
| `settings.py` | ClearML project layout constants; `SHIP_TARGET` (TBD) |

## Config

`CLEARML_*` values come from `core.config.Settings` (declared in `.env.example`).
The `clearml` SDK dependency is not in `pyproject.toml` yet — add it when
`tracking/` gets its first real implementation.

## Open decisions

- **Runtime hand-off** — how a consuming context receives the shipped bundle:
  in-process pull via `mlops.interface` (ClearML off the request path), publish to
  MinIO, or a direct ClearML pull. `settings.SHIP_TARGET` selects it.
- Whether draft candidates live only in ClearML or also as `bundle_version` rows
  from creation (`service.record_candidate` currently assumes the latter).
- Per-kind scorers, gates, and eval-set formats.

## Wiring left to do

- `main_web.py` lifespan: call `mlops.db.init_models()`; `app.include_router(mlops.router)`.
- `main_worker.py`: dispatch `mlops.jobs.*`.
- `tests/mlops/conftest.py`: in-memory SQLite wiring (copy `tests/knowledge/conftest.py`).
