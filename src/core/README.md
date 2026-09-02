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

Layout (one subpackage per concern; grows as `core` takes on more):

```
src/core/
├── api.py              # health router (mounted by main_web)
├── config.py           # Settings + get_settings() — typed env access
├── db.py               # engine / SessionLocal / Base / get_session dep / init_models()
├── security/           # crypto mechanism, no domain knowledge
│   ├── password.py     # hash_password / verify_password (PBKDF2-HMAC-SHA256, stdlib)
│   └── jwt.py          # create_access_token / decode_access_token (PyJWT, HS256)
└── users/              # user identity + JWT auth policy — owns auth.users
    ├── models.py       # User (id, email, name, hashed_password, is_active, timestamps)
    ├── schemas.py      # UserCreate / UserRead / Token
    ├── service.py      # create_user / authenticate_user / get_user_by_*
    ├── dependencies.py # oauth2_scheme, get_current_user, get_current_active_user, CurrentUser
    └── api.py          # router: POST /auth/register, POST /auth/token, GET /auth/me
```

### Auth usage

Other contexts inject the dependency in their own `api.py`:

```python
from core.users import CurrentUser  # Annotated[User, Depends(get_current_active_user)]

@router.get("/plants")
def list_plants(user: CurrentUser) -> ...:
    ...
```

`POST /auth/token` takes an OAuth2 password form (`username` = email), so the
**Authorize** button in `/docs` works. `main_web` mounts the `/auth` router
alongside the health router.

Until per-schema Alembic migrations land, `core.db.init_models()` creates the
`auth` schema and its tables directly (used by tests; call it once for a local
run against Postgres).
