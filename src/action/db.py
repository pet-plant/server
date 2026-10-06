"""SQLAlchemy wiring for the ``action`` schema.

Same arrangement as the other contexts: the engine and pool come from
:mod:`core.db`, the metadata is local. Until per-schema Alembic migrations land,
:func:`init_models` creates the schema and its tables directly.
"""

from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase

from core.db import engine as _core_engine

ACTION_SCHEMA = "action"

if _core_engine.dialect.name == "postgresql":
    engine = _core_engine
else:
    # SQLite has no schemas: fold ``action`` into the default one.
    _existing = _core_engine.get_execution_options().get("schema_translate_map", {})
    engine = _core_engine.execution_options(schema_translate_map={**_existing, ACTION_SCHEMA: None})


def utcnow() -> datetime:
    """Timezone-aware 'now', used as a column default."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for tables owned by the ``action`` context."""


def init_models() -> None:
    """Create the ``action`` schema and its tables. Interim until Alembic."""
    from action import models  # noqa: F401  -- register models on Base.metadata

    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{ACTION_SCHEMA}"'))
        Base.metadata.create_all(conn)
