# core — infrastructure kernel

**Package:** `src/core/`
**Part of context 8 (System Integration & Infrastructure).** Not a domain
context — it has no business rules and no domain tables.

## Responsibilities

- **Configuration**: load and validate settings from the environment
  (see `.env.example`); expose typed config to every context.
- **Database**: SQLAlchemy engine / session lifecycle; per-schema migration
  tooling and wiring (each context supplies its own migrations).
- **Object storage**: MinIO / S3 client and bucket accessors.
- **Auth**: OAuth2 / JWT token issuance and verification; owns the `auth` schema
  (identities, roles, device bindings). Exposes the FastAPI auth dependencies that
  each context applies in its own `api.py`.
- **Health**: `core/api.py` provides the `router` that `main_web` mounts for
  `GET /health` (liveness; readiness to follow).
- **Observability**: logging setup, request/job context, error reporting.
- **Shared primitives**: common base classes, error types, time/id utilities.

## Rules

- Depends on no other context.
- Provides mechanism, not policy — it does not know about plants, probes or moods.

## Internal design

Left to the core owner, within the rules above.
