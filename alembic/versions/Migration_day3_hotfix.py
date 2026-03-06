"""
Day 3 Hotfix — Add missing columns to knowledge_bases

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-06

Fixes:
  - knowledge_bases.created_by   → was in model but never in migration
  - knowledge_bases.compiled_content → needed by KB routes preview endpoint
  - knowledge_bases.word_count       → needed by KB schema response
  - knowledge_bases.source_document_ids → needed by KB schema
  - knowledge_bases.car_model_ids    → needed by KB schema
  - knowledge_bases.elevenlabs_kb_id → needed by KB schema
  - knowledge_bases.last_synced_at   → needed by KB schema
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c AND table_schema='public'"
    ), {"t": table, "c": column}).fetchone()
    return result is not None


def _add_col(table, col_name, col_type, nullable=True, server_default=None):
    if _column_exists(table, col_name):
        return
    op.add_column(table, sa.Column(col_name, col_type, nullable=True))
    if server_default is not None:
        op.execute(sa.text(
            f"UPDATE {table} SET {col_name} = {server_default} WHERE {col_name} IS NULL"
        ))
    if not nullable and server_default is not None:
        op.alter_column(table, col_name, nullable=False,
                        server_default=sa.text(server_default))


def upgrade() -> None:
    # ── knowledge_bases missing columns ───────────────────────────────────────
    _add_col("knowledge_bases", "created_by",
             postgresql.UUID(as_uuid=True))

    _add_col("knowledge_bases", "compiled_content",
             sa.Text)

    _add_col("knowledge_bases", "word_count",
             sa.Integer)

    _add_col("knowledge_bases", "source_document_ids",
             sa.Text)   # JSON string

    _add_col("knowledge_bases", "car_model_ids",
             sa.Text)   # JSON string

    _add_col("knowledge_bases", "elevenlabs_kb_id",
             sa.String(255))

    _add_col("knowledge_bases", "last_synced_at",
             sa.TIMESTAMP)

    # Backfill created_by with the dealership owner's user_id
    # so existing rows don't violate any NOT NULL constraints later
    op.execute(sa.text("""
        UPDATE knowledge_bases kb
        SET created_by = d.user_id
        FROM dealerships d
        WHERE kb.dealership_id = d.dealership_id
          AND kb.created_by IS NULL
    """))


def downgrade() -> None:
    for col in [
        "created_by", "compiled_content", "word_count",
        "source_document_ids", "car_model_ids",
        "elevenlabs_kb_id", "last_synced_at"
    ]:
        try:
            op.drop_column("knowledge_bases", col)
        except Exception:
            pass