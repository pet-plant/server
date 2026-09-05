# knowledge — Species & Care Knowledge (context 3)

**Package:** `src/knowledge/`

Botanical knowledge base. A person researches a species and writes what they
found as free text; that text is fed to an LLM, which turns it into **probes**
(single-question checks) and the **actions** to take when each one fires.
Few-shot **exemplar images** for the probes are kept in MinIO.

- **Owns (Postgres schema):** `knowledge`
- **Owns (MinIO):** `exemplars`
- **Feeds:** `assessment` (probes), `advice` (actions)
- **Calls out:** external LLM for probe generation (text only, never images)

Nothing here is edited in place or deleted. Revising the research text inserts a
new row and archives the one it replaces; approving another probe set archives
the set it replaces. A species therefore has exactly one **active** document and
at most one **approved** probe set, and every superseded version stays on record
— an archived probe set can be approved again to swap it back in.

## Data model

```
species
  └── research_document      human-written research text — the LLM input, kept verbatim
        └── probe_set        one LLM generation run (model, prompt version, approval, status)
              └── probe      one single-question check (care_need, question, worse/better/not_this, …)
                    ├── probe_action     what to do when it fires (+ how long the effect takes)
                    └── probe_exemplar   few-shot image: object key in the `exemplars` bucket + label
```

| Table | Holds |
|-------|-------|
| `species` | `species_code` (`'spath'`), scientific / common name |
| `research_document` | `title`, `body` (the researched text), `content_hash`, `author`, source URL/note, `status` (`active`/`archived`), `created_at`, `archived_at` |
| `probe_set` | FK to the document, `species_code`, `source_content_hash`, `llm_model`, `prompt_version`, `status` (`draft`/`approved`/`archived`), `generated_at`, `approved_by` / `approved_at`, `archived_at` |
| `probe` | FK to the set, `slug` (unique per set), `care_need`, `crop`, `priority`, `is_screening`, `question`, `worse_looks_like`, `better_looks_like`, `not_this`, `evidence_quote` |
| `probe_action` | FK to the probe, `instruction`, `urgency`, `expect_typical_hours`, `expect_max_hours` (grace period), `expected_signal` |
| `probe_exemplar` | FK to the probe, `role`, `storage_key` (in the `exemplars` bucket), `content_type`, `label` (JSONB), `origin`, `license`, `caption` |

### Singletons enforced in the database

Two partial unique indexes carry the rule; the service layer archives the
incumbent (with `archived_at`) before promoting its replacement, so the swap is
one transaction:

```sql
CREATE UNIQUE INDEX uq_research_document_active_species
    ON knowledge.research_document (species_code) WHERE status = 'active';
CREATE UNIQUE INDEX uq_probe_set_approved_species
    ON knowledge.probe_set (species_code) WHERE status = 'approved';
```

Drafts and archived rows are unconstrained — any number may exist per species.

`probe_set.species_code` is denormalised from its research document so the index
above can be a database constraint. A composite foreign key back to
`research_document (id, species_code)` (backed by a `UNIQUE (id, species_code)`
on the parent) makes it impossible for the two to disagree.

### Keeping probes in sync with the document

`content_hash` is `SHA-256(body)`, filled in automatically on insert. Every
`probe_set` snapshots it as `source_content_hash` at generation time. The current
document for a species is its `active` row.

The `probe_set_freshness` view compares each set's snapshot against the active
document's hash and exposes `is_stale`:

```sql
SELECT * FROM knowledge.probe_set_freshness
WHERE status = 'approved' AND is_stale;   -- the approved set's source text moved on
```

It flags *when to regenerate and re-review* — it does not judge whether the
probes are correct; that is still the human `approved_by` step. Prompt/model
changes are not covered here — compare `llm_model` / `prompt_version` if you need
that too.

## HTTP API (`/knowledge`, mounted by `main_web`)

All endpoints require an authenticated **superuser** (`core.users.CurrentSuperuser`)
— this is the authoring surface, not something plant owners call. The LLM
generation logic is **not** wired yet, so there is no "create probe set" endpoint.

| Method & path | Purpose |
|---|---|
| `POST /knowledge/species` | register a species (409 if `species_code` is taken) |
| `GET /knowledge/species` | list registered species |
| `POST /knowledge/documents` | add a research document; the species' previous one is archived (404 if `species_code` is unknown) |
| `GET /knowledge/documents?species_code=&status=` | list documents, newest first; `status` is `active` or `archived` |
| `GET /knowledge/documents/{id}` | one document (active or archived) |
| `GET /knowledge/species/{species_code}/probe-sets` | every probe set for the species with `status`, `is_stale`, `probe_count` |
| `GET /knowledge/probe-sets/{id}` | one set with its probes, each carrying `actions` and `exemplars` |
| `POST /knowledge/probe-sets/{id}/approve` | make this the species' approved set, archiving the incumbent (`approved_by` = caller's email); works from `draft` **and** from `archived` (swapping an older set back in); 409 if already approved or it has no probes |
| `POST /knowledge/probe-sets/{id}/archive` | `approved` → `archived`, leaving the species with no approved set; 409 otherwise |
| `GET /knowledge/species/{species_code}/probes` | the approved bundle — same payload as the interface below |

There is no `PATCH` or `DELETE` for documents: a correction is a new document,
and the superseded text stays readable as an archived row.

### Authoring flow

`register species → write research document → (LLM job builds a draft probe set —
not wired yet) → approve`. `/species/{code}/probes` and the in-process interface
only ever return the **approved** set; approving another one archives the
previous automatically, and approving an archived one rolls back.

## Published interface (in-process)

```python
from knowledge import get_species_probes   # (session, species_code) -> SpeciesProbesBundle | None

bundle = get_species_probes(session, "spath")
bundle.model_dump(mode="json")   # -> {species_code, probe_set_id, status, is_stale, generated_at, probes: [...]}
```

Returns the species' **approved** probe set (with every probe's actions and
exemplars), or `None` if there is none. `assessment` and `advice` call this
instead of touching the `knowledge` schema.

## Internal design

```
src/knowledge/
├── api.py              # /knowledge router (document authoring + probe inspection)
├── interface.py        # get_species_probes() — the in-process interface
├── service.py          # DB reads/writes; no HTTP, no LLM
├── schemas.py          # Pydantic request/response + interface payloads
├── db.py               # KNOWLEDGE_SCHEMA, Base (own MetaData), JsonB, utcnow(),
│                       #   probe_set_freshness (view handle), create_views(), init_models()
├── hashing.py          # content_hash(body) -> sha256 hex
└── models/
    ├── species.py      # Species
    ├── document.py     # ResearchDocument
    ├── probe.py        # ProbeSet, Probe
    ├── action.py       # ProbeAction
    └── exemplar.py     # ProbeExemplar
```

- `db.py` reuses `core.db`'s engine / pool but keeps its **own** declarative
  `Base`, so `knowledge` metadata stays isolated from the `auth` schema.
- Surrogate `uuid` primary keys everywhere except `species` (whose
  `species_code` is a real domain identifier).
- `JsonB` = `jsonb` on PostgreSQL, `json` on SQLite (local checks / tests).
- Foreign keys are declared for every parent link. The one cross-column rule —
  `probe_exemplar.license` required when `origin = 'web'` — is left to the
  service layer for now and can become a DB `CHECK` later.
- Enum-like columns (`status`, `care_need`, `crop`, `role`, `urgency`, `origin`)
  are plain `text`; the partial unique indexes above are what the status values
  are actually load-bearing for.
- ORM `relationship()`s connect each parent to its children, with
  `cascade="all, delete-orphan"` down `probe_set → probe → action/exemplar`
  (deleting a set removes everything under it). `species → documents` and
  `document → probe_sets` have no cascade — and nothing in the API deletes rows
  anyway; superseded rows are archived instead.
- `probe_set_freshness` is a SQL **view**, not a table; `db.py` holds a
  read-only `Table` handle for it in a separate `MetaData` so
  `Base.metadata.create_all` never tries to build it.

Until per-schema Alembic migrations land, `knowledge.db.init_models()` creates
the `knowledge` schema, its tables and the `probe_set_freshness` view directly
(used by tests; call once for a local Postgres run).
