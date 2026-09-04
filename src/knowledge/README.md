# knowledge — Species & Care Knowledge (context 3)

**Package:** `src/knowledge/`

Botanical knowledge base. A person researches a species and writes what they
found as free text; that text is fed to an LLM, which turns it into **metrics**
(single-question probes) and the **actions** to take when each one fires.
Few-shot **exemplar images** for the metrics are kept in MinIO.

- **Owns (Postgres schema):** `knowledge`
- **Owns (MinIO):** `exemplars`
- **Feeds:** `assessment` (metrics), `advice` (actions)
- **Calls out:** external LLM for metric generation (text only, never images)

## Data model

```
species
  └── research_document      human-written research text — the LLM input, kept verbatim
        └── metric_set        one LLM generation run (model, prompt version, approval, status)
              └── metric      one single-question probe (care_need, question, worse/better/not_this, …)
                    ├── metric_action     what to do when it fires (+ how long the effect takes)
                    └── metric_exemplar   few-shot image: object key in the `exemplars` bucket + label
```

| Table | Holds |
|-------|-------|
| `species` | `species_code` (`'spath'`), scientific / common name |
| `research_document` | `title`, `body` (the researched text), `content_hash`, `author`, source URL/note, `created_at` |
| `metric_set` | FK to the document, `source_content_hash`, `llm_model`, `prompt_version`, `status` (`draft`/`approved`/`archived`), `generated_at`, `approved_by` / `approved_at` |
| `metric` | FK to the set, `slug` (unique per set), `care_need`, `crop`, `priority`, `is_screening`, `question`, `worse_looks_like`, `better_looks_like`, `not_this`, `evidence_quote` |
| `metric_action` | FK to the metric, `instruction`, `urgency`, `expect_typical_hours`, `expect_max_hours` (grace period), `expected_signal` |
| `metric_exemplar` | FK to the metric, `role`, `storage_key` (in the `exemplars` bucket), `content_type`, `label` (JSONB), `origin`, `license`, `caption` |

Re-running the LLM (better text, better prompt) produces a **new** `metric_set`;
`status` marks which one is live. Old sets are kept, not overwritten.

### Keeping metrics in sync with the document

`content_hash` is `SHA-256(body)`, filled in automatically on insert and
recomputed by the service whenever `body` is edited. Every `metric_set` snapshots
it as `source_content_hash` at generation time. The current document for a
species is the newest `created_at` row (one active document per species is
assumed — editing in place and inserting a new row both work).

The `metric_set_freshness` view compares each set's snapshot against the current
document's hash and exposes `is_stale`:

```sql
SELECT * FROM knowledge.metric_set_freshness
WHERE status = 'approved' AND is_stale;   -- approved sets whose source text moved on
```

It flags *when to regenerate and re-review* — it does not judge whether the
metrics are correct; that is still the human `approved_by` step. Prompt/model
changes are not covered here — compare `llm_model` / `prompt_version` if you need
that too.

## HTTP API (`/knowledge`, mounted by `main_web`)

All endpoints require an authenticated active user (`core.users.CurrentUser`).
The LLM generation logic is **not** wired yet — these only read and edit what is
already stored, so there is no "create metric set" endpoint.

| Method & path | Purpose |
|---|---|
| `POST /knowledge/documents` | create a research document (404 if `species_code` is unknown) |
| `GET /knowledge/documents?species_code=` | list documents, newest first |
| `GET /knowledge/documents/{id}` | one document |
| `PATCH /knowledge/documents/{id}` | edit fields; changing `body` recomputes `content_hash` (→ dependent metric sets show `is_stale`) |
| `DELETE /knowledge/documents/{id}` | delete (409 if a metric set still references it) |
| `GET /knowledge/species/{species_code}/metric-sets` | every metric set for the species with `status`, `is_stale`, `metric_count` |
| `GET /knowledge/metric-sets/{id}` | one set with its metrics, each carrying `actions` and `exemplars` |
| `GET /knowledge/species/{species_code}/metrics` | the current bundle — same payload as the interface below |

## Published interface (in-process)

```python
from knowledge import get_species_metrics   # (session, species_code) -> SpeciesMetricsBundle | None

bundle = get_species_metrics(session, "spath")
bundle.model_dump(mode="json")   # -> {species_code, metric_set_id, status, is_stale, generated_at, metrics: [...]}
```

Returns the most recent **approved** metric set for the species (with every
metric's actions and exemplars), or `None` if there is none. `assessment` and
`advice` call this instead of touching the `knowledge` schema.

## Internal design

```
src/knowledge/
├── api.py              # /knowledge router (document CRUD + metric inspection)
├── interface.py        # get_species_metrics() — the in-process interface
├── service.py          # DB reads/writes; no HTTP, no LLM
├── schemas.py          # Pydantic request/response + interface payloads
├── db.py               # KNOWLEDGE_SCHEMA, Base (own MetaData), JsonB, utcnow(),
│                       #   metric_set_freshness (view handle), create_views(), init_models()
├── hashing.py          # content_hash(body) -> sha256 hex
└── models/
    ├── species.py      # Species
    ├── document.py     # ResearchDocument
    ├── metric.py       # MetricSet, Metric
    ├── action.py       # MetricAction
    └── exemplar.py     # MetricExemplar
```

- `db.py` reuses `core.db`'s engine / pool but keeps its **own** declarative
  `Base`, so `knowledge` metadata stays isolated from the `auth` schema.
- Surrogate `uuid` primary keys everywhere except `species` (whose
  `species_code` is a real domain identifier).
- `JsonB` = `jsonb` on PostgreSQL, `json` on SQLite (local checks / tests).
- Foreign keys are declared for every parent link. The one cross-column rule —
  `metric_exemplar.license` required when `origin = 'web'` — is left to the
  service layer for now and can become a DB `CHECK` later.
- Enum-like columns (`status`, `care_need`, `crop`, `role`, `urgency`, `origin`)
  are plain `text`; `metric_set` versioning is what keeps them consistent.
- ORM `relationship()`s connect each parent to its children, with
  `cascade="all, delete-orphan"` down `metric_set → metric → action/exemplar`
  (deleting a set removes everything under it). `species → documents` and
  `document → metric_sets` have no cascade — deleting a referenced document is
  refused (409) instead.
- `metric_set_freshness` is a SQL **view**, not a table; `db.py` holds a
  read-only `Table` handle for it in a separate `MetaData` so
  `Base.metadata.create_all` never tries to build it.

Until per-schema Alembic migrations land, `knowledge.db.init_models()` creates
the `knowledge` schema, its tables and the `metric_set_freshness` view directly
(used by tests; call once for a local Postgres run).
