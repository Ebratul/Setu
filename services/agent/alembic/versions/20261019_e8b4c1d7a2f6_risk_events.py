"""risk_events table; FUND_ESCROW and CONFIRM_MILESTONES approval actions

Revision ID: e8b4c1d7a2f6
Revises: d5a3f0c8b7e1
Create Date: 2026-10-19 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e8b4c1d7a2f6'
down_revision: Union[str, Sequence[str], None] = 'd5a3f0c8b7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIONS_OLD = ["RELEASE_MILESTONE", "CHANGE_BENEFICIARY", "LOCK_FX_RATE", "CHANGE_MILESTONE_SCHEDULE", "ACCEPT_FINANCING"]
ACTIONS_NEW = ACTIONS_OLD + ["FUND_ESCROW", "CONFIRM_MILESTONES"]


def _in(values: list[str]) -> str:
    return f"action IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_approval_requests_approval_action'), 'approval_requests', type_='check')
    op.create_check_constraint(op.f('ck_approval_requests_approval_action'), 'approval_requests', _in(ACTIONS_NEW))
    op.create_table(
        'risk_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deal_id', sa.Uuid(), nullable=True),
        sa.Column('milestone_id', sa.Uuid(), nullable=True),
        sa.Column('actor_user_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('origin', sa.String(length=16), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('tier', sa.SmallInteger(), nullable=False),
        sa.Column('reason_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('explanation_en', sa.String(length=600), nullable=False),
        sa.Column('explanation_bn', sa.String(length=900), nullable=False),
        sa.Column('context_hash', sa.CHAR(length=64), nullable=False),
        sa.Column('trace', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('hints', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('amount_usd', sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column('audit_seq', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_risk_events_actor_user_id_users')),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_risk_events_deal_id_deals'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['milestone_id'], ['milestones.id'], name=op.f('fk_risk_events_milestone_id_milestones'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_risk_events')),
    )
    op.create_index(op.f('ix_risk_events_ts'), 'risk_events', ['ts'])
    op.create_index(op.f('ix_risk_events_deal_id'), 'risk_events', ['deal_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_risk_events_deal_id'), table_name='risk_events')
    op.drop_index(op.f('ix_risk_events_ts'), table_name='risk_events')
    op.drop_table('risk_events')
    op.execute("DELETE FROM approval_requests WHERE action IN ('FUND_ESCROW', 'CONFIRM_MILESTONES')")
    op.drop_constraint(op.f('ck_approval_requests_approval_action'), 'approval_requests', type_='check')
    op.create_check_constraint(op.f('ck_approval_requests_approval_action'), 'approval_requests', _in(ACTIONS_OLD))
