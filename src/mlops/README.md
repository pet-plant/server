# 7. Evaluation & MLOps

**Package:** `src/mlops/`
**Role:** AI quality assurance — evaluate VLM/LLM outputs and probe accuracy, and
govern which bundles reach production. Implements MR-5 (LLMOps with ClearML).
**Owner:** _TBD_

## Responsibilities

- Manage frozen evaluation sets (~150–250 labelled image pairs) for testing.
- Execute evaluation runs to validate VLM/LLM outputs and probe accuracy
  (accuracy and abstention rate, reported honestly).
- Handle promotion gates so bundle upgrades are safe and verified; rollback is a
  retag.
- Version bundles together: metric scripts, probe prompts, exemplar sets, model
  versions, thresholds — evaluated as one artifact.
- Accumulate owner corrections as new evaluation cases and candidate exemplars;
  re-evaluate the bundle against the grown set on a schedule.

Backed by self-hosted **ClearML** (Tasks, ClearML-Data, Model Registry), kept
inside the project's own infrastructure boundary.

## Data it owns

- PostgreSQL schema `mlops`: labelled cases, evaluation episodes/results,
  promotion records, bundle-version registry (metadata; artifacts in ClearML).
- MinIO: `eval-sets` (frozen labelled pairs); reads `exemplars`.

## Inputs

- Candidate bundles from `knowledge`.
- Owner corrections (via HTTP, `ops` role).

## Outputs

- **Validate VLM** → `assessment`; **Validate LLM** → `advice`.
- Promoted bundle tags that `assessment` / `advice` consume in production.

## Driven by

- `main_worker` (evaluate-and-promote cycle, scheduled re-evaluation), often via a
  ClearML Agent.

## HTTP surface

This context owns `src/mlops/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `mlops` schema from outside.
