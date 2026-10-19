"""privacy_records: masked transparency records (no token vault)

Revision ID: a7d2c9e4b1f8
Revises: f1c7a3b9d204
Create Date: 2026-10-20 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7d2c9e4b1f8'
down_revision: Union[str, Sequence[str], None] = 'f1c7a3b9d204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'privacy_records',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('thread_id', sa.Uuid(), nullable=True),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        sa.Column('document_id', sa.Uuid(), nullable=True),
        sa.Column('run_id', sa.String(length=64), nullable=True),
        sa.Column('node', sa.String(length=32), nullable=False),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('sent', sa.Boolean(), nullable=False),
        sa.Column('masked_payload', sa.Text(), nullable=False),
        sa.Column('masked_output', sa.Text(), nullable=True),
        sa.Column('masked_by_type', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('protected', sa.Integer(), nullable=False),
        sa.Column('leaked', sa.Integer(), nullable=False),
        sa.Column('chars_sent', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_privacy_records_user_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['thread_id'], ['chat_threads.id'], name=op.f('fk_privacy_records_thread_id_chat_threads'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['chat_messages.id'], name=op.f('fk_privacy_records_message_id_chat_messages'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_privacy_records_document_id_documents'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_privacy_records')),
    )
    for col in ('created_at', 'user_id', 'thread_id', 'message_id', 'document_id'):
        op.create_index(op.f(f'ix_privacy_records_{col}'), 'privacy_records', [col])


def downgrade() -> None:
    for col in ('document_id', 'message_id', 'thread_id', 'user_id', 'created_at'):
        op.drop_index(op.f(f'ix_privacy_records_{col}'), table_name='privacy_records')
    op.drop_table('privacy_records')
