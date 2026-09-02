# orchestrator — orchestration & sync

**Package:** `src/orchestrator/`
**Part of context 8 (System Integration & Infrastructure).**

## Responsibilities

- **Event bus / message routing**: asynchronous communication between contexts
  and between the cloud and the edge. Routes the edge capture-batch upload to
  `capture`; carries pipeline hand-offs where a step is event-driven; delivers
  `companion` mood/utterance updates back to the edge display (presentation sync).
- **Batch-workflow coordination**: defines and dispatches the job catalogue that
  `main_worker` runs (drain capture batches, run probe battery, refresh script
  bundles, evaluate-and-promote, …).
- **Device sync**: keeps edge devices and the cloud in agreement on what to
  render and what to capture.
- Owns its own schema (`orchestrator`): event outbox / log, job runs, device-sync
  state.

## Contracts

Message and job contracts are defined here jointly with the producing and
consuming contexts. The fixed pipeline order is
`capture → assessment → advice → companion`.

## HTTP surface

If this context exposes HTTP (e.g. device-sync endpoints), the routes live in
`src/orchestrator/api.py` exposing `router: APIRouter`; `main_web` mounts it.

## Internal design

Left to the orchestrator owner (event-bus technology, delivery guarantees, job
runner) within the contracts above.
