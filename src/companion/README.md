# 6. Companion

**Package:** `src/companion/`
**Role:** Ambient UI & persona — express the plant's condition and needs as a
character, not a dashboard, and acknowledge care the owner performs.
**Owner:** _TBD_

## Responsibilities

- Map internal states to character moods and expressions (a five-state character).
- Drive the non-verbal animation shown on the planter's ambient display to
  indicate status quietly.
- Manage the interaction loop and text utterances, speaking only when data
  crosses critical thresholds; keep the character from repeating itself.
- Process care acknowledgements from the owner and reflect them (e.g. move to
  `recovering` once the next cycle returns `better`).

The character may express only what the system has actually observed.

## Data it owns

- PostgreSQL schema `companion`: mood/expression state, utterance history,
  care acknowledgements, interaction log.
- MinIO: none.

## Inputs

- **Diagnosis & actions** (+ character line) from `advice`.
- Care acknowledgements and non-verbal interaction events (via HTTP / edge).

## Outputs

- **Mood state & text** → `orchestrator` → edge display (presentation sync).

## Driven by

- `orchestrator` events (new advice) and `main_web` (acknowledgements,
  interaction events).

## HTTP surface

This context owns `src/companion/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `companion` schema from outside.
