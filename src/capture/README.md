# 2. Capture & Vision

**Package:** `src/capture/`
**Role:** Visual data extraction — turn uploaded frames into clean, comparable
inputs for assessment. (This is the **cloud** vision pipeline; the on-device
capture agent lives in the edge repository.)
**Owner:** _TBD_

## Responsibilities

- Receive capture batches uploaded from the edge (scheduled, several times a day,
  no manual intervention) and quality-check them.
- Preprocess frames.
- Segment the plant from the domestic background (on-prem segmentation service at
  `SEGMENTATION_ENDPOINT`; model not in this repo), producing named crops
  (e.g. `whole_plant`, `canopy_upper`, `canopy_lower`, `leaf_closeup_k`,
  `soil_surface`).
- Register and align the current frame against the reference so the two are
  directly comparable; composite onto a single labelled canvas where the VLM
  handles one image better than two.

## Data it owns

- PostgreSQL schema `vision`: capture-batch and frame metadata, alignment
  references, quality results.
- MinIO: `captures` (raw frames), `frames-derived` (crops, aligned/composited
  canvases). Captures are retained.

## Inputs

- Capture-batch uploads, routed in by `orchestrator`.
- Plant identity / anchor from `registry`.

## Outputs

- **Extracted features** (segmented, aligned frames + crop manifest) → `assessment`.

## Driven by

- `orchestrator` events (batch arrived) and `main_worker` (drain pending batches).

## HTTP surface

This context owns `src/capture/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `vision` schema from outside.
