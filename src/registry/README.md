# 1. Plant Registry

**Package:** `src/registry/`
**Role:** Identity & physical anchoring — the persistent record of which physical
plant is which.
**Owner:** _TBD_

## Responsibilities

- Identify and persist the physical existence of a plant (who, what, where).
- Manage plant profiles: species assignment (resolved once at registration,
  confirmed by the owner, then cached — never re-run) and owner mapping.
- Calibrate and manage camera placement and anchor identity so the system keeps
  tracking the same physical plant over time.

## Data it owns

- PostgreSQL schema `registry`: plants, owners, species assignment, camera
  placement / anchor.
- MinIO: none.

## Inputs

- Owner registration requests (via HTTP).
- Species identification from the on-prem VLM API (`VLM_API_BASE`, served with
  vLLM; model not in this repo) — once, at registration.

## Outputs

- **Plant identity** → `assessment` (and any context that needs the resolved
  species / anchor).

## Driven by

- `main_web` (owner and device API requests).

## HTTP surface

This context owns `src/registry/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `registry` schema from outside.
