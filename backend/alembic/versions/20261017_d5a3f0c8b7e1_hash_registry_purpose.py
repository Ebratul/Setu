"""hash_registry: purposes, status, semantic fingerprint; documents unique per deal

Revision ID: d5a3f0c8b7e1
Revises: 26b582a72d5c
Create Date: 2026-10-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd5a3f0c8b7e1'
down_revision: Union[str, Sequence[str], None] = '26b582a72d5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.drop_constraint('uq_hash_registry_canonical_hash_lender_party_id', 'hash_registry', type_='unique')
    op.alter_column('hash_registry', 'canonical_hash', new_column_name='semantic_fingerprint', nullable=True)
    op.alter_column('hash_registry', 'lender_party_id', nullable=True)
    op.alter_column('hash_registry', 'external_ref', nullable=True)
    op.add_column('hash_registry', sa.Column('purpose', sa.Enum('ESCROW_EVIDENCE', 'FINANCING_COLLATERAL', name='registry_purpose', native_enum=False, create_constraint=True, length=32), nullable=False, server_default='FINANCING_COLLATERAL'))
    op.add_column('hash_registry', sa.Column('context_key', sa.String(length=100), nullable=True))
    op.add_column('hash_registry', sa.Column('document_id', sa.Uuid(), nullable=True))
    op.add_column('hash_registry', sa.Column('registered_by_user_id', sa.Uuid(), nullable=True))
    op.add_column('hash_registry', sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('hash_registry', sa.Column('seen_count', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('hash_registry', sa.Column('status', sa.Enum('ACTIVE', 'RELEASED', name='registry_status', native_enum=False, create_constraint=True, length=32), nullable=False, server_default='ACTIVE'))
    op.add_column('hash_registry', sa.Column('released_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('hash_registry', sa.Column('exact_hits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('hash_registry', sa.Column('near_hits', sa.Integer(), nullable=False, server_default='0'))
    op.execute(
        "UPDATE hash_registry SET context_key = purpose || ':' || COALESCE(lender_party_id::text, '-')"
        " || ':' || COALESCE(deal_id::text, '-')"
    )
    op.alter_column('hash_registry', 'context_key', nullable=False)
    op.execute(
        "INSERT INTO hash_registry (id, sha256, semantic_fingerprint, doc_type, purpose, context_key,"
        " deal_id, document_id, registered_at, seen_count, status, exact_hits, near_hits)"
        " SELECT gen_random_uuid(), d.sha256, d.canonical_hash, d.doc_type::text, 'ESCROW_EVIDENCE',"
        " 'ESCROW_EVIDENCE:-:' || d.deal_id::text, d.deal_id, d.id, COALESCE(d.uploaded_at, now()),"
        " 1, 'ACTIVE', 0, 0 FROM documents d WHERE d.status = 'UPLOADED' AND d.sha256 IS NOT NULL"
        " AND d.check_status <> 'FAILED' ON CONFLICT DO NOTHING"
    )
    for col in ('purpose', 'seen_count', 'status', 'exact_hits', 'near_hits'):
        op.alter_column('hash_registry', col, server_default=None)
    op.create_foreign_key(op.f('fk_hash_registry_document_id_documents'), 'hash_registry', 'documents', ['document_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_hash_registry_registered_by_user_id_users'), 'hash_registry', 'users', ['registered_by_user_id'], ['id'], ondelete='SET NULL')
    op.create_unique_constraint(op.f('uq_hash_registry_sha256_context_key'), 'hash_registry', ['sha256', 'context_key'])
    op.create_index(op.f('ix_hash_registry_semantic_fingerprint'), 'hash_registry', ['semantic_fingerprint'], unique=False)
    op.create_index(op.f('ix_hash_registry_status'), 'hash_registry', ['status'], unique=False)

    op.drop_constraint('uq_documents_sha256', 'documents', type_='unique')
    op.create_unique_constraint(op.f('uq_documents_deal_id'), 'documents', ['deal_id', 'sha256'])
    op.create_index(op.f('ix_documents_sha256'), 'documents', ['sha256'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documents_sha256'), table_name='documents')
    op.drop_constraint(op.f('uq_documents_deal_id'), 'documents', type_='unique')
    # The old constraint allowed one row per file: later copies on other deals lose their hash.
    op.execute(
        "UPDATE documents d SET sha256 = NULL WHERE sha256 IS NOT NULL AND EXISTS ("
        "SELECT 1 FROM documents e WHERE e.sha256 = d.sha256"
        " AND (e.uploaded_at, e.id) < (d.uploaded_at, d.id))"
    )
    op.create_unique_constraint('uq_documents_sha256', 'documents', ['sha256'])
    op.drop_index(op.f('ix_hash_registry_status'), table_name='hash_registry')
    op.drop_index(op.f('ix_hash_registry_semantic_fingerprint'), table_name='hash_registry')
    op.drop_constraint(op.f('uq_hash_registry_sha256_context_key'), 'hash_registry', type_='unique')
    op.drop_constraint(op.f('fk_hash_registry_registered_by_user_id_users'), 'hash_registry', type_='foreignkey')
    op.drop_constraint(op.f('fk_hash_registry_document_id_documents'), 'hash_registry', type_='foreignkey')
    for col in ('near_hits', 'exact_hits', 'released_at', 'status', 'seen_count', 'last_seen_at',
                'registered_by_user_id', 'document_id', 'context_key', 'purpose'):
        op.drop_column('hash_registry', col)
    op.execute("DELETE FROM hash_registry WHERE lender_party_id IS NULL")
    op.alter_column('hash_registry', 'external_ref', nullable=False)
    op.alter_column('hash_registry', 'lender_party_id', nullable=False)
    op.execute("UPDATE hash_registry SET semantic_fingerprint = sha256 WHERE semantic_fingerprint IS NULL")
    op.alter_column('hash_registry', 'semantic_fingerprint', new_column_name='canonical_hash', nullable=False)
    op.create_unique_constraint('uq_hash_registry_canonical_hash_lender_party_id', 'hash_registry', ['canonical_hash', 'lender_party_id'])
