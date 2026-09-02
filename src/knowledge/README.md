# 3. Species & Care Knowledge

**Package:** `src/knowledge/`
**Role:** Botanical knowledge base — the curated care knowledge and the probe /
metric-script bundles derived from it.
**Owner:** _TBD_

## Responsibilities

- Catalogue botanical knowledge: species definitions and their specific care
  needs.
- Define probes for assessing plant health. Metric scripts are generated
  **offline** (an external LLM grounded by retrieval over the care knowledge
  base), reviewed, and versioned — never generated at inference time. The
  generator may return `probe: null` with a reason when a care need has no valid
  visual probe.
- Manage knowledge sources; package care needs + probe prompts + exemplar sets
  into versioned **script bundles**.
- Handle offline editing, versioning and updating of care knowledge.

## Data it owns

- PostgreSQL schema `knowledge`: care needs, probe / metric-script definitions,
  bundles and versions, knowledge sources.
- MinIO: `exemplars` (versioned few-shot exemplar images).

## Inputs

- Curated care knowledge and owner corrections (via HTTP, `ops` role).
- External LLM (text only) for offline script generation.

## Outputs

- **Probe definitions** (script bundle for a species) → `assessment`.

## Driven by

- `main_web` (`ops` authoring) and `main_worker` (offline bundle generation /
  refresh).

## HTTP surface

This context owns `src/knowledge/api.py` exposing `router: APIRouter`, plus its own
request/response schemas (organised however the owner prefers). `main_web` mounts
the router; routes apply the auth dependencies provided by `core`.

## Internal design

Left to the context owner. Other contexts use only this context's published
interface; no access to the `knowledge` schema from outside.
