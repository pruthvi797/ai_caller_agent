"""
Day 6 — Calls Table Migration
==============================

Revision ID: d4e5f6a7b8c9
Down Revision: c3d4e5f6a7b8  (Day 5 migration)

Replaces the Day 1 stub calls table with the full Day 6 schema.

Strategy: Idempotent — checks if each column already exists before adding it.
Safe to run multiple times without breaking.

New columns added vs Day 1 stub:
  dealership_id         UUID FK → dealerships
  elevenlabs_agent_id   String — which EL agent made the call
  conversation_id       String — EL conversation ID (unique)
  phone_number          String — number actually called (E.164)
  call_duration_seconds Integer — renamed from call_duration
  initiated_at          TIMESTAMP — when EL accepted
  connected_at          TIMESTAMP — when customer answered
  ended_at              TIMESTAMP — when call ended
  transcript_json       JSONB — structured turn-by-turn
  call_recording_url    String(500)
  interest_score        Integer 0-10
  test_drive_requested  Boolean
  pricing_asked         Boolean
  variant_asked         Boolean
  exchange_enquired     Boolean
  emi_enquired          Boolean
  competing_model_mentioned  String
  ai_summary            Text
  attempt_number        Integer
  scheduled_at          TIMESTAMP
  webhook_payload       JSONB
  error_message         Text
  initiated_by          UUID FK → users
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists (for idempotent migrations)."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.fetchone() is not None


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes WHERE indexname = :i"
        ),
        {"i": index_name},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # ── Ensure table exists (in case Day 1 migration created it differently) ──
    conn = op.get_bind()
    table_exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'calls'"
        )
    ).fetchone()

    if not table_exists:
        # Create the full table from scratch
        op.create_table(
            "calls",
            sa.Column("call_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("dealership_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dealerships.dealership_id"), nullable=False),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("campaigns.campaign_id"), nullable=False),
            sa.Column("lead_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("leads.lead_id"), nullable=False),
            sa.Column("elevenlabs_agent_id", sa.String(255), nullable=True),
            sa.Column("conversation_id", sa.String(255), nullable=True),
            sa.Column("phone_number", sa.String(20), nullable=False),
            sa.Column("call_status", sa.String(30), nullable=False, server_default="queued"),
            sa.Column("call_outcome", sa.String(50), nullable=True),
            sa.Column("call_duration_seconds", sa.Integer, nullable=True),
            sa.Column("initiated_at", sa.TIMESTAMP, nullable=True),
            sa.Column("connected_at", sa.TIMESTAMP, nullable=True),
            sa.Column("ended_at", sa.TIMESTAMP, nullable=True),
            sa.Column("transcript", sa.Text, nullable=True),
            sa.Column("transcript_json", postgresql.JSON, nullable=True),
            sa.Column("call_recording_url", sa.String(500), nullable=True),
            sa.Column("interest_score", sa.Integer, nullable=True),
            sa.Column("test_drive_requested", sa.Boolean, nullable=True),
            sa.Column("pricing_asked", sa.Boolean, nullable=True),
            sa.Column("variant_asked", sa.Boolean, nullable=True),
            sa.Column("exchange_enquired", sa.Boolean, nullable=True),
            sa.Column("emi_enquired", sa.Boolean, nullable=True),
            sa.Column("competing_model_mentioned", sa.String(150), nullable=True),
            sa.Column("ai_summary", sa.Text, nullable=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
            sa.Column("scheduled_at", sa.TIMESTAMP, nullable=True),
            sa.Column("webhook_payload", postgresql.JSON, nullable=True),
            sa.Column("initiated_by", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP, nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP, nullable=False),
        )
    else:
        # Table exists — add missing columns idempotently
        new_columns = [
            ("dealership_id",               postgresql.UUID(as_uuid=True)),
            ("elevenlabs_agent_id",         sa.String(255)),
            ("conversation_id",             sa.String(255)),
            ("phone_number",                sa.String(20)),
            ("call_duration_seconds",       sa.Integer),
            ("initiated_at",                sa.TIMESTAMP),
            ("connected_at",                sa.TIMESTAMP),
            ("ended_at",                    sa.TIMESTAMP),
            ("transcript_json",             postgresql.JSON),
            ("call_recording_url",          sa.String(500)),
            ("interest_score",              sa.Integer),
            ("test_drive_requested",        sa.Boolean),
            ("pricing_asked",               sa.Boolean),
            ("variant_asked",               sa.Boolean),
            ("exchange_enquired",           sa.Boolean),
            ("emi_enquired",                sa.Boolean),
            ("competing_model_mentioned",   sa.String(150)),
            ("ai_summary",                  sa.Text),
            ("error_message",               sa.Text),
            ("attempt_number",              sa.Integer),
            ("scheduled_at",                sa.TIMESTAMP),
            ("webhook_payload",             postgresql.JSON),
            ("initiated_by",                postgresql.UUID(as_uuid=True)),
        ]

        for col_name, col_type in new_columns:
            if not _column_exists("calls", col_name):
                op.add_column("calls", sa.Column(col_name, col_type, nullable=True))

        # Rename call_duration → call_duration_seconds if old name exists
        if _column_exists("calls", "call_duration") and not _column_exists("calls", "call_duration_seconds"):
            op.alter_column("calls", "call_duration", new_column_name="call_duration_seconds")

        # Ensure call_status default
        op.alter_column("calls", "call_status",
                        existing_type=sa.String(30),
                        server_default="queued",
                        nullable=False)

    # ── Indexes ───────────────────────────────────────────────────────────────
    indexes = [
        ("ix_calls_campaign_id",    "calls", ["campaign_id"]),
        ("ix_calls_lead_id",        "calls", ["lead_id"]),
        ("ix_calls_dealership_id",  "calls", ["dealership_id"]),
        ("ix_calls_call_status",    "calls", ["call_status"]),
        ("ix_calls_conversation_id","calls", ["conversation_id"]),
    ]

    for idx_name, tbl, cols in indexes:
        if not _index_exists(idx_name):
            op.create_index(idx_name, tbl, cols)

    # ── Unique constraint on conversation_id ──────────────────────────────────
    if not _index_exists("uq_calls_conversation_id"):
        op.create_index(
            "uq_calls_conversation_id",
            "calls",
            ["conversation_id"],
            unique=True,
            postgresql_where=sa.text("conversation_id IS NOT NULL"),
        )


def downgrade() -> None:
    # Drop new indexes
    for idx in [
        "uq_calls_conversation_id",
        "ix_calls_conversation_id",
        "ix_calls_call_status",
        "ix_calls_dealership_id",
        "ix_calls_lead_id",
        "ix_calls_campaign_id",
    ]:
        try:
            op.drop_index(idx, table_name="calls")
        except Exception:
            pass

    # Drop new columns (leave original stub columns)
    new_cols = [
        "dealership_id", "elevenlabs_agent_id", "conversation_id", "phone_number",
        "call_duration_seconds", "initiated_at", "connected_at", "ended_at",
        "transcript_json", "call_recording_url", "interest_score",
        "test_drive_requested", "pricing_asked", "variant_asked",
        "exchange_enquired", "emi_enquired", "competing_model_mentioned",
        "ai_summary", "error_message", "attempt_number", "scheduled_at",
        "webhook_payload", "initiated_by",
    ]
    for col in new_cols:
        try:
            op.drop_column("calls", col)
        except Exception:
            pass
