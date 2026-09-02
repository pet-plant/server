# 4. Assessment

**Package:** `src/assessment/`
**Role:** Internal-state inference — run the probe battery on the VLM and turn
raw vision data into a structured, confidence-qualified plant state.
**Owner:** _TBD_

## Responsibilities

- Execute probes against the VLM (on-prem, served with vLLM via an
  OpenAI-compatible API — the model is not part of this repository) using
  extracted vision data, one probe per call, with each probe's few-shot
  exemplars. A cheap screening probe gates the full battery.
- Compare against both a curated healthy anchor and a frame from seven days
  earlier.
- Aggregate N repeated runs (non-zero temperature) into an objective **verdict**
  (`worse` / `same` / `better` / `cannot_tell`) and **severity** (0–3, omitted
  when `cannot_tell`).
- Gather **evidence** (one sentence naming what changed and where) and compute
  agreement / observation metrics; low-agreement probes abstain rather than guess.
- Translate the probe results into the plant's internal state, accumulating
  history so downstream sees a trend, not a snapshot.

## Data it owns

- PostgreSQL schema `assessment`: probe runs, verdicts, severities, evidence,
  agreement/confidence, per-plant probe history.
- MinIO: none (reads derived frames via `capture`).

## Inputs

- **Extracted features** from `capture`.
- **Probe definitions** (script bundle) from `knowledge`.
- **Plant identity** from `registry`.
- Bundle under test from `mlops` during validation.
- VLM inference via the on-prem vLLM API (`VLM_API_BASE`).

## Outputs

- **Internal state & verdicts** (structured probe results + trend) → `advice`.

## Driven by

- `orchestrator` events / `main_worker` (run battery for a cycle).

## HTTP surface

This context owns `src/assessment/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `assessment` schema from outside.
