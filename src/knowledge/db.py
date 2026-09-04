"""SQLAlchemy wiring for the ``knowledge`` schema.

The context owns the ``knowledge`` Postgres schema. Every model inherits from
:class:`Base` (a declarative base distinct from ``core``'s ``auth`` base, so this
schema's table metadata stays context-local) and sets
``{"schema": KNOWLEDGE_SCHEMA}`` in ``__table_args__``.

The engine and connection pool come from :mod:`core.db`; only the metadata is
local here. Until per-schema Alembic migrations land, :func:`init_models` creates
the schema, its tables and the ``metric_set_freshness`` view directly — enough
for local runs and tests.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    Connection,
    Integer,
    MetaData,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

from core.db import engine as _core_engine

KNOWLEDGE_SCHEMA = "knowledge"

#: ``jsonb`` on PostgreSQL; ``json`` on SQLite (local quick-checks and tests).
JsonB = JSONB().with_variant(JSON(), "sqlite")

if _core_engine.dialect.name == "postgresql":
    engine = _core_engine
else:
    # SQLite has no schemas: fold ``knowledge`` (alongside whatever ``core``
    # already folded) into the default schema so the qualified models run
    # unchanged for local checks.
    _existing = _core_engine.get_execution_options().get("schema_translate_map", {})
    engine = _core_engine.execution_options(
        schema_translate_map={**_existing, KNOWLEDGE_SCHEMA: None}
    )


def utcnow() -> datetime:
    """Timezone-aware 'now', used as a column default."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for tables owned by the ``knowledge`` context."""


# A metric set is "stale" when the hash it was generated from no longer matches
# the current research document for that species (the newest ``created_at`` row).
# See the ``knowledge`` README.
_FRESHNESS_VIEW_SQL = """
CREATE VIEW {prefix}metric_set_freshness AS
SELECT
    ms.id                  AS metric_set_id,
    ms.research_document_id,
    ms.status,
    ms.source_content_hash,
    cur.id                 AS current_document_id,
    cur.content_hash       AS current_content_hash,
    CASE WHEN ms.source_content_hash <> cur.content_hash THEN 1 ELSE 0 END AS is_stale
FROM {prefix}metric_set ms
JOIN {prefix}research_document used ON used.id = ms.research_document_id
JOIN {prefix}research_document cur
      ON cur.species_code = used.species_code
     AND cur.created_at = (
         SELECT MAX(d.created_at)
         FROM {prefix}research_document d
         WHERE d.species_code = used.species_code
     )
"""


def create_views(conn: Connection) -> None:
    """(Re)create the ``knowledge`` SQL views on an open connection."""
    prefix = f"{KNOWLEDGE_SCHEMA}." if conn.dialect.name == "postgresql" else ""
    conn.execute(text(f"DROP VIEW IF EXISTS {prefix}metric_set_freshness"))
    conn.execute(text(_FRESHNESS_VIEW_SQL.format(prefix=prefix)))


# Read-only handle on the view above, for SELECTs from the service layer. Kept in
# its own MetaData so ``Base.metadata.create_all`` never tries to build it as a
# table; schema translation still applies on SQLite via the engine options.
_views_metadata = MetaData()
metric_set_freshness = Table(
    "metric_set_freshness",
    _views_metadata,
    Column("metric_set_id", Uuid, primary_key=True),
    Column("research_document_id", Uuid),
    Column("status", Text),
    Column("source_content_hash", Text),
    Column("current_document_id", Uuid),
    Column("current_content_hash", Text),
    Column("is_stale", Integer),
    schema=KNOWLEDGE_SCHEMA,
)


def init_models() -> None:
    """Create the ``knowledge`` schema, tables and views. Interim until Alembic."""
    from knowledge import models  # noqa: F401  -- register models on Base.metadata

    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{KNOWLEDGE_SCHEMA}"'))
        Base.metadata.create_all(conn)
        create_views(conn)
