"""
Day 5 Migration — ElevenLabs Agent Configuration
=================================================

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-06

Upgrades agent_config table with full ElevenLabs integration fields:
  - elevenlabs_agent_id   : ElevenLabs agent ID (from create agent API)
  - voice_id              : ElevenLabs voice ID
  - voice_name            : Human-readable voice name
  - first_message         : Opening greeting
  - knowledge_base_id     : FK to knowledge_bases table
  - elevenlabs_kb_id      : ElevenLabs KB document ID (from create KB doc API)
  - kb_synced_at          : When KB was last pushed
  - kb_sync_status        : pending | synced | failed
  - kb_sync_error         : Error message if sync failed
  - language              : Call language (en | hi | te | ta | kn)
  - max_call_duration_secs: Safety limit on call length
  - stability             : ElevenLabs TTS voice stability
  - similarity_boost      : ElevenLabs TTS voice clarity
  - dealership_id         : FK to dealerships (for ownership checks)
  - created_by            : FK to users
  - status                : draft | configured | ready | error
  - error_message         : Last error details

Safe/idempotent — uses _column_exists checks before adding columns.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd5e6f7g8h9i0'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _table_exists(table_name: str) -> bool:
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name=:t AND table_schema='public'"
    ), {"t": table_name}).fetchone()
    return result is not None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name=:t AND column_name=:c AND table_schema='public'"
    ), {"t": table, "c": column}).fetchone()
    return result is not None


def _index_exists(index_name: str) -> bool:
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname=:i"
    ), {"i": index_name}).fetchone()
    return result is not None


def _add_col(table, col_name, col_type, nullable=True, server_default=None):
    if _column_exists(table, col_name):
        return
    op.add_column(table, sa.Column(col_name, col_type, nullable=True))
    if server_default is not None:
        op.execute(sa.text(
            f"UPDATE {table} SET {col_name} = {server_default} WHERE {col_name} IS NULL"
        ))


def _add_index(index_name, table, *columns):
    if not _index_exists(index_name):
        op.create_index(index_name, table, list(columns))


# ══════════════════════════════════════════════════════════════════════════════
# UPGRADE
# ══════════════════════════════════════════════════════════════════════════════

def upgrade() -> None:

    # ── agent_config — create or upgrade ──────────────────────────────────────
    if not _table_exists("agent_config"):
        op.create_table(
            "agent_config",

            # ── Primary key ──────────────────────────────────────────────────
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), primary_key=True),

            # ── Ownership ────────────────────────────────────────────────────
            sa.Column(
                "campaign_id", postgresql.UUID(as_uuid=True),
                sa.ForeignKey("campaigns.campaign_id"),
                nullable=False, unique=True,
            ),
            sa.Column(
                "dealership_id", postgresql.UUID(as_uuid=True),
                sa.ForeignKey("dealerships.dealership_id"),
                nullable=False,
            ),
            sa.Column(
                "created_by", postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.user_id"),
                nullable=True,
            ),

            # ── ElevenLabs agent ─────────────────────────────────────────────
            sa.Column("elevenlabs_agent_id", sa.String(255), nullable=True),
            sa.Column("voice_id", sa.String(255), nullable=False,
                      server_default="cgSgspJ2msm6clMCkdW9"),
            sa.Column("voice_name", sa.String(100), nullable=True,
                      server_default="Jessica"),

            # ── Prompts ──────────────────────────────────────────────────────
            sa.Column("system_prompt", sa.Text, nullable=False,
                      server_default="You are a Suzuki sales representative."),
            sa.Column("first_message", sa.Text, nullable=True),

            # ── Knowledge base ───────────────────────────────────────────────
            sa.Column(
                "knowledge_base_id", postgresql.UUID(as_uuid=True),
                sa.ForeignKey("knowledge_bases.kb_id"),
                nullable=True,
            ),
            sa.Column("elevenlabs_kb_id", sa.String(255), nullable=True),
            sa.Column("kb_synced_at", sa.TIMESTAMP, nullable=True),
            sa.Column("kb_sync_status", sa.String(30), nullable=True),
            sa.Column("kb_sync_error", sa.Text, nullable=True),

            # ── Conversation settings ─────────────────────────────────────────
            sa.Column("language", sa.String(10), nullable=False, server_default="en"),
            sa.Column("max_call_duration_secs", sa.Integer, nullable=False,
                      server_default="300"),
            sa.Column("stability", sa.Float, nullable=False, server_default="0.5"),
            sa.Column("similarity_boost", sa.Float, nullable=False, server_default="0.75"),

            # ── Status ───────────────────────────────────────────────────────
            sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
            sa.Column("error_message", sa.Text, nullable=True),

            # ── Audit ────────────────────────────────────────────────────────
            sa.Column("created_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
        )

    else:
        # ── Upgrade existing stub table ────────────────────────────────────────
        # Original stub had: agent_id, campaign_id, voice, system_prompt,
        #                    knowledge_base_id (String), created_at, updated_at

        _add_col("agent_config", "dealership_id", postgresql.UUID(as_uuid=True))
        _add_col("agent_config", "created_by", postgresql.UUID(as_uuid=True))
        _add_col("agent_config", "elevenlabs_agent_id", sa.String(255))
        _add_col("agent_config", "voice_id", sa.String(255),
                 server_default="'cgSgspJ2msm6clMCkdW9'")
        _add_col("agent_config", "voice_name", sa.String(100),
                 server_default="'Jessica'")
        _add_col("agent_config", "first_message", sa.Text)

        # knowledge_base_id was String in stub — change to UUID FK
        # Safe: add new UUID column, keep old String column (nullable)
        _add_col("agent_config", "kb_uuid_id", postgresql.UUID(as_uuid=True))

        _add_col("agent_config", "elevenlabs_kb_id", sa.String(255))
        _add_col("agent_config", "kb_synced_at", sa.TIMESTAMP)
        _add_col("agent_config", "kb_sync_status", sa.String(30))
        _add_col("agent_config", "kb_sync_error", sa.Text)
        _add_col("agent_config", "language", sa.String(10), server_default="'en'")
        _add_col("agent_config", "max_call_duration_secs", sa.Integer,
                 server_default="300")
        _add_col("agent_config", "stability", sa.Float, server_default="0.5")
        _add_col("agent_config", "similarity_boost", sa.Float, server_default="0.75")
        _add_col("agent_config", "status", sa.String(30), server_default="'draft'")
        _add_col("agent_config", "error_message", sa.Text)

    # ── Indexes ───────────────────────────────────────────────────────────────
    _add_index("ix_agent_config_campaign_id", "agent_config", "campaign_id")
    _add_index("ix_agent_config_dealership_id", "agent_config", "dealership_id")
    _add_index("ix_agent_config_status", "agent_config", "status")


def downgrade() -> None:
    # Only safe to drop entirely if this is a fresh table from this migration
    op.drop_table("agent_config")
