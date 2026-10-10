"""001 init extensions and schemas

Revision ID: 001_init_ext_schemas
Revises:
Create Date: 2026-10-09 19:40:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_init_ext_schemas'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMAS = [
    "auth",
    "registry",
    "knowledge",
    "action",
    "orchestrator",
    "assessment",
    "advice",
    "companion",
]


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # 2. Create bounded context schemas
    for schema in SCHEMAS:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}";'))


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;'))
    op.execute(sa.text("DROP EXTENSION IF EXISTS vector;"))
