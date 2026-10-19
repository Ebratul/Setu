"""approval OTP/expiry columns, LOCKED status, approval_events, demo_phone_messages

Revision ID: f1c7a3b9d204
Revises: e8b4c1d7a2f6
Create Date: 2026-10-19 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f1c7a3b9d204'
down_revision: Union[str, Sequence[str], None] = 'e8b4c1d7a2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_OLD = ["PENDING", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED", "EXPIRED"]
STATUS_NEW = STATUS_OLD + ["LOCKED"]


def _in(values: list[str]) -> str:
    return f"status IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_approval_requests_approval_status'), 'approval_requests', type_='check')
    op.create_check_constraint(op.f('ck_approval_requests_approval_status'), 'approval_requests', _in(STATUS_NEW))
    op.add_column('approval_requests', sa.Column('context_hash', sa.CHAR(length=64), nullable=True))
    op.add_column('approval_requests', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('approval_requests', sa.Column('otp_hash', sa.CHAR(length=64), nullable=True))
    op.add_column('approval_requests', sa.Column('otp_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('approval_requests', sa.Column('otp_attempts', sa.SmallInteger(), server_default='0', nullable=False))
    op.add_column('approval_requests', sa.Column('otp_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('approval_requests', sa.Column('decision_note', sa.String(length=300), nullable=True))
    op.add_column('approval_requests', sa.Column('superseded_by', sa.Uuid(), nullable=True))
    op.create_table(
        'approval_events',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('party_id', sa.Uuid(), nullable=True),
        sa.Column('deal_id', sa.Uuid(), nullable=True),
        sa.Column('approval_id', sa.Uuid(), nullable=True),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('tier', sa.SmallInteger(), nullable=False),
        sa.Column('actor', sa.String(length=8), nullable=False),
        sa.Column('title_en', sa.String(length=200), nullable=False),
        sa.Column('title_bn', sa.String(length=200), nullable=False),
        sa.Column('detail_en', sa.String(length=600), nullable=False),
        sa.Column('detail_bn', sa.String(length=900), nullable=False),
        sa.Column('audit_seq', sa.BigInteger(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_approval_events_party_id_parties'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deal_id'], ['deals.id'], name=op.f('fk_approval_events_deal_id_deals'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approval_id'], ['approval_requests.id'], name=op.f('fk_approval_events_approval_id_approval_requests'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_approval_events')),
    )
    op.create_index(op.f('ix_approval_events_ts'), 'approval_events', ['ts'])
    op.create_index(op.f('ix_approval_events_party_id'), 'approval_events', ['party_id'])
    op.create_index(op.f('ix_approval_events_deal_id'), 'approval_events', ['deal_id'])
    op.create_index(op.f('ix_approval_events_approval_id'), 'approval_events', ['approval_id'])
    op.create_table(
        'demo_phone_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('party_id', sa.Uuid(), nullable=False),
        sa.Column('approval_id', sa.Uuid(), nullable=True),
        sa.Column('body', sa.String(length=300), nullable=False),
        sa.Column('code', sa.String(length=6), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['party_id'], ['parties.id'], name=op.f('fk_demo_phone_messages_party_id_parties'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['approval_id'], ['approval_requests.id'], name=op.f('fk_demo_phone_messages_approval_id_approval_requests'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_demo_phone_messages')),
    )
    op.create_index(op.f('ix_demo_phone_messages_party_id'), 'demo_phone_messages', ['party_id'])
    op.create_index(op.f('ix_demo_phone_messages_approval_id'), 'demo_phone_messages', ['approval_id'])


def downgrade() -> None:
    op.drop_table('demo_phone_messages')
    op.drop_table('approval_events')
    for col in ('superseded_by', 'decision_note', 'otp_verified_at', 'otp_attempts', 'otp_expires_at',
                'otp_hash', 'expires_at', 'context_hash'):
        op.drop_column('approval_requests', col)
    op.execute("UPDATE approval_requests SET status = 'CANCELLED' WHERE status = 'LOCKED'")
    op.drop_constraint(op.f('ck_approval_requests_approval_status'), 'approval_requests', type_='check')
    op.create_check_constraint(op.f('ck_approval_requests_approval_status'), 'approval_requests', _in(STATUS_OLD))
