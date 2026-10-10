"""002 create care plan action table

Revision ID: 002_care_plan_action
Revises: 001_init_ext_schemas
Create Date: 2026-10-09 20:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '002_care_plan_action'
down_revision: Union[str, None] = '001_init_ext_schemas'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'care_plan_action',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('care_plan_pk', sa.Uuid(), nullable=False),
        sa.Column('care_plan_id', sa.Text(), nullable=False),
        sa.Column('action_id', sa.Text(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('action_type', sa.Text(), nullable=False, server_default='other'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['care_plan_pk'],
            ['advice.care_plan.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema='advice',
    )
    op.create_index(
        'ix_care_plan_action_plan_id',
        'care_plan_action',
        ['care_plan_id'],
        schema='advice',
    )
    op.create_index(
        'ix_care_plan_action_plan_pk',
        'care_plan_action',
        ['care_plan_pk'],
        schema='advice',
    )


def downgrade() -> None:
    op.drop_index('ix_care_plan_action_plan_pk', table_name='care_plan_action', schema='advice')
    op.drop_index('ix_care_plan_action_plan_id', table_name='care_plan_action', schema='advice')
    op.drop_table('care_plan_action', schema='advice')
