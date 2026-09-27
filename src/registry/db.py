"""SQLAlchemy wiring for the ``registry`` schema.

The context owns the ``registry`` Postgres schema. Every model inherits from
:class:`Base` (a declarative base distinct from ``core``'s and ``knowledge``'s, so
this schema's table metadata stays context-local) and sets
``{"schema": REGISTRY_SCHEMA}`` in ``__table_args__``.

The engine and connection pool come from :mod:`core.db`; only the metadata is
local here. Until per-schema Alembic migrations land, :func:`init_models` creates
the schema and its tables directly — enough for local runs and tests.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

from core.db import engine as _core_engine

REGISTRY_SCHEMA = "registry"

if _core_engine.dialect.name == "postgresql":
    engine = _core_engine
else:
    # SQLite has no schemas: fold ``registry`` (alongside whatever ``core``
    # already folded) into the default schema so the qualified models run
    # unchanged for local checks.
    _existing = _core_engine.get_execution_options().get("schema_translate_map", {})
    engine = _core_engine.execution_options(
        schema_translate_map={**_existing, REGISTRY_SCHEMA: None}
    )


def utcnow() -> datetime:
    """Timezone-aware 'now', used as a column default."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for tables owned by the ``registry`` context."""


def init_models() -> None:
    """Create the ``registry`` schema and its tables. Interim until Alembic."""
    from registry import models  # noqa: F401  -- register models on Base.metadata

    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{REGISTRY_SCHEMA}"'))
        Base.metadata.create_all(conn)
