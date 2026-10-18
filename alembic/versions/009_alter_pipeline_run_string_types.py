"""009 alter pipeline_run columns to specific varchar types

Revision ID: 009_pipeline_run_types
Revises: 008_drop_unused
Create Date: 2026-10-18 17:50:00.000000

Changes:
- orchestrator.pipeline_run.trigger: TEXT -> VARCHAR(16)
- orchestrator.pipeline_run.status: TEXT -> VARCHAR(16)
- orchestrator.pipeline_run.current_stage: TEXT -> VARCHAR(32)
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_pipeline_run_types"
down_revision: str | None = "008_drop_unused"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "pipeline_run",
        "trigger",
        type_=sa.String(16),
        existing_type=sa.Text(),
        existing_nullable=False,
        schema="orchestrator",
    )
    op.alter_column(
        "pipeline_run",
        "status",
        type_=sa.String(16),
        existing_type=sa.Text(),
        existing_nullable=False,
        schema="orchestrator",
    )
    op.alter_column(
        "pipeline_run",
        "current_stage",
        type_=sa.String(32),
        existing_type=sa.Text(),
        existing_nullable=False,
        schema="orchestrator",
    )


def downgrade() -> None:
    op.alter_column(
        "pipeline_run",
        "current_stage",
        type_=sa.Text(),
        existing_type=sa.String(32),
        existing_nullable=False,
        schema="orchestrator",
    )
    op.alter_column(
        "pipeline_run",
        "status",
        type_=sa.Text(),
        existing_type=sa.String(16),
        existing_nullable=False,
        schema="orchestrator",
    )
    op.alter_column(
        "pipeline_run",
        "trigger",
        type_=sa.Text(),
        existing_type=sa.String(16),
        existing_nullable=False,
        schema="orchestrator",
    )
