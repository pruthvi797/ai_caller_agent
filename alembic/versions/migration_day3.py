"""Add documents, document_chunks, knowledge_bases tables

Revision ID: a1b2c3d4e5f6
Revises: d3461f5f9dc5
Create Date: 2026-03-05

Day 3 — Document Management & Knowledge Base
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'a1b2c3d4e5f6'
down_revision = 'd3461f5f9dc5'
branch_labels = None
depends_on = None


def _column_exists(table, column):
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).fetchone()
    return result is not None


def _index_exists(index_name):
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname=:i"
    ), {"i": index_name}).fetchone()
    return result is not None


def _add_col(table, col_name, col_type, nullable=True, default_sql=None):
    """
    Safely add a column to an existing table with data.
    Steps:
      1. Add as nullable (no default) — always safe for existing rows
      2. UPDATE existing rows with the default value
      3. ALTER to NOT NULL + server_default if required
    """
    if _column_exists(table, col_name):
        return

    op.add_column(table, sa.Column(col_name, col_type, nullable=True))

    if default_sql is not None:
        op.execute(
            sa.text(f"UPDATE {table} SET {col_name} = {default_sql} WHERE {col_name} IS NULL")
        )

    if not nullable and default_sql is not None:
        op.alter_column(table, col_name, nullable=False,
                        server_default=sa.text(default_sql))
    elif not nullable:
        op.alter_column(table, col_name, nullable=False)
    elif default_sql is not None:
        op.alter_column(table, col_name, server_default=sa.text(default_sql))


def upgrade() -> None:

    # ─────────────────────────────────────────────────────────────────────────
    # documents
    # Existing columns: document_id, car_model_id, file_name, file_type,
    #                   file_path, processed_text, uploaded_at, created_at,
    #                   updated_at
    # ─────────────────────────────────────────────────────────────────────────

    # dealership_id — critical FK, nullable for now (existing rows have no value)
    _add_col("documents", "dealership_id",     sa.UUID())

    # filename — our new name for file_name (keep file_name, just add filename)
    _add_col("documents", "filename",          sa.String(255))
    _add_col("documents", "stored_filename",   sa.String(255))
    _add_col("documents", "file_size_bytes",   sa.BigInteger())
    _add_col("documents", "mime_type",         sa.String(100))
    _add_col("documents", "uploaded_by",       sa.UUID())
    _add_col("documents", "processed_at",      sa.TIMESTAMP())

    # classification
    _add_col("documents", "document_type",     sa.String(50),  nullable=False, default_sql="'brochure'")
    _add_col("documents", "title",             sa.String(255))
    _add_col("documents", "description",       sa.Text())

    # processing pipeline
    _add_col("documents", "processing_status", sa.String(30),  nullable=False, default_sql="'pending'")
    _add_col("documents", "processing_error",  sa.Text())
    _add_col("documents", "extracted_text",    sa.Text())
    _add_col("documents", "chunk_count",       sa.Integer(),   default_sql="0")

    # status / soft-delete
    _add_col("documents", "is_active",         sa.Boolean(),   nullable=False, default_sql="true")
    _add_col("documents", "deleted_at",        sa.TIMESTAMP())

    # indexes (only on columns that now exist)
    if not _index_exists("ix_documents_dealership_id"):
        op.create_index("ix_documents_dealership_id", "documents", ["dealership_id"])
    if not _index_exists("ix_documents_car_model_id"):
        op.create_index("ix_documents_car_model_id", "documents", ["car_model_id"])
    if not _index_exists("ix_documents_processing_status"):
        op.create_index("ix_documents_processing_status", "documents", ["processing_status"])

    # ─────────────────────────────────────────────────────────────────────────
    # document_chunks
    # Existing columns: chunk_id, document_id, chunk_text, embedding, created_at
    # ─────────────────────────────────────────────────────────────────────────

    _add_col("document_chunks", "dealership_id", sa.UUID())
    _add_col("document_chunks", "car_model_id",  sa.UUID())
    _add_col("document_chunks", "chunk_index",   sa.Integer(), default_sql="0")
    _add_col("document_chunks", "section_type",  sa.String(50))
    _add_col("document_chunks", "char_count",    sa.Integer())

    if not _index_exists("ix_document_chunks_document_id"):
        op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    if not _index_exists("ix_document_chunks_dealership_id"):
        op.create_index("ix_document_chunks_dealership_id", "document_chunks", ["dealership_id"])
    if not _index_exists("ix_document_chunks_section_type"):
        op.create_index("ix_document_chunks_section_type", "document_chunks", ["section_type"])

    # ─────────────────────────────────────────────────────────────────────────
    # knowledge_bases — brand new table
    # ─────────────────────────────────────────────────────────────────────────
    op.create_table(
        'knowledge_bases',
        sa.Column('kb_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('dealership_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('dealerships.dealership_id'), nullable=False),

        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),

        sa.Column('compiled_content', sa.Text, nullable=True),
        sa.Column('source_document_ids', sa.Text, nullable=True),
        sa.Column('car_model_ids', sa.Text, nullable=True),
        sa.Column('total_chunks', sa.Integer, nullable=True, server_default='0'),
        sa.Column('word_count', sa.Integer, nullable=True),

        sa.Column('status', sa.String(30), nullable=False, server_default='draft'),
        sa.Column('compile_error', sa.Text, nullable=True),

        sa.Column('elevenlabs_kb_id', sa.String(255), nullable=True),
        sa.Column('last_synced_at', sa.TIMESTAMP, nullable=True),

        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP, nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.TIMESTAMP, nullable=False,
                  server_default=sa.text('NOW()')),
    )
    op.create_index('ix_knowledge_bases_dealership_id', 'knowledge_bases', ['dealership_id'])
    op.create_index('ix_knowledge_bases_status', 'knowledge_bases', ['status'])


def downgrade() -> None:
    op.drop_table('knowledge_bases')
    # We don't remove added columns on downgrade to avoid data loss