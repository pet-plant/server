# 5. Care Advice

**Package:** `src/advice/`
**Role:** Interpretable reasoning & action — turn verdicts plus history into
specific, ordered care actions with their reasoning.
**Owner:** _TBD_

## Responsibilities

- Analyse the current observations and this plant's history to produce a specific
  **diagnosis**.
- Recommend ordered, actionable steps with a calculated **urgency**.
- Provide explicit **rationale and citations**, grounding the LLM's reasoning in
  the extracted vision data and the care knowledge base (retrieval-grounded).
- Turn an abstaining probe into a question to the owner rather than a guess;
  escalate when prior advice went unheeded.
- Produce the character's words for `companion`.

## Data it owns

- PostgreSQL schema `advice`: diagnoses, actions, rationale, citations, advice
  history (what was advised, when, whether the owner marked it done).
- MinIO: none.

## Inputs

- **Internal state & verdicts** from `assessment`.
- Care knowledge (for retrieval / citations) from `knowledge`.
- External LLM — **text only, never images**.

## Outputs

- **Diagnosis & actions** (+ character line) → `companion`.

## Driven by

- `orchestrator` events / `main_worker` (advise for a completed assessment cycle).

## HTTP surface

This context owns `src/advice/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `advice` schema from outside.
