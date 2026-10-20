"""injection_events: readable log of prompt-injection detections and dropped tool calls

Revision ID: b3e8d5a1c7f2
Revises: a7d2c9e4b1f8
Create Date: 2026-10-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b3e8d5a1c7f2'
down_revision: Union[str, Sequence[str], None] = 'a7d2c9e4b1f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'injection_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('origin', sa.String(length=16), nullable=False),
        sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('score', sa.SmallInteger(), nullable=False),
        sa.Column('snippet', sa.String(length=200), nullable=False),
        sa.Column('attack_style', sa.String(length=32), nullable=True),
        sa.Column('tool', sa.String(length=64), nullable=True),
        sa.Column('action_taken', sa.String(length=32), nullable=False),
        sa.Column('layer', sa.SmallInteger(), nullable=True),
        sa.Column('defences_on', sa.Boolean(), nullable=False),
        sa.Column('flags_deal', sa.Boolean(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deal_id', sa.Uuid(), nullable=True),
        sa.Column('document_id', sa.Uuid(), nullable=True),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('audit_seq', sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_injection_events_deal_id_deals'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_injection_events_document_id_documents'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_injection_events_user_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_injection_events')),
    )
    op.create_index(op.f('ix_injection_events_ts'), 'injection_events', ['ts'])
    op.create_index(op.f('ix_injection_events_attack_style'), 'injection_events', ['attack_style'])
    op.create_index(op.f('ix_injection_events_flags_deal'), 'injection_events', ['flags_deal'])
    op.create_index(op.f('ix_injection_events_deal_id'), 'injection_events', ['deal_id'])


def downgrade() -> None:
    op.drop_table('injection_events')
