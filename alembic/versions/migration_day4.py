"""
Day 4 Migration — Campaigns, Leads, Campaign Documents
=======================================================

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-06

Adds:
  - campaigns table (upgraded with all business fields)
  - leads table (upgraded with full lead management fields)
  - campaign_documents table (with linking metadata)

Uses safe _add_col / _table_exists helpers so it's idempotent —
safe to run even if partial columns already exist from the stub models.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


# ── Helpers (same pattern as migration_day3.py) ────────────────────────────────

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
    if not nullable and server_default is not None:
        op.alter_column(table, col_name, nullable=False,
                        server_default=sa.text(server_default))
    elif not nullable:
        op.alter_column(table, col_name, nullable=False)


def _add_index(index_name, table, *columns):
    if not _index_exists(index_name):
        op.create_index(index_name, table, list(columns))


def upgrade() -> None:

    # ══════════════════════════════════════════════════════════════════════════
    # campaigns
    # ══════════════════════════════════════════════════════════════════════════

    if not _table_exists("campaigns"):
        op.create_table(
            "campaigns",
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                      primary_key=True),
            sa.Column("dealership_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dealerships.dealership_id"), nullable=False),
            sa.Column("created_by", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.user_id"), nullable=False),
            sa.Column("car_model_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("car_models.car_model_id"), nullable=True),
            sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("knowledge_bases.kb_id"), nullable=True),
            sa.Column("campaign_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("promotion_type", sa.String(50), nullable=False,
                      server_default="general_inquiry"),
            sa.Column("start_date", sa.Date, nullable=False),
            sa.Column("end_date", sa.Date, nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("daily_call_limit", sa.Integer, nullable=True),
            sa.Column("calling_hours", sa.String(20), nullable=True,
                      server_default="09:00-21:00"),
            sa.Column("language", sa.String(30), nullable=True, server_default="english"),
            sa.Column("total_leads", sa.Integer, nullable=False, server_default="0"),
            sa.Column("leads_called", sa.Integer, nullable=False, server_default="0"),
            sa.Column("leads_interested", sa.Integer, nullable=False, server_default="0"),
            sa.Column("leads_converted", sa.Integer, nullable=False, server_default="0"),
            sa.Column("internal_notes", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("deleted_at", sa.TIMESTAMP, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
        )
    else:
        # Table exists (from stub model) — add missing columns safely
        _add_col("campaigns", "created_by", postgresql.UUID(as_uuid=True))
        _add_col("campaigns", "knowledge_base_id", postgresql.UUID(as_uuid=True))
        _add_col("campaigns", "description", sa.Text)
        _add_col("campaigns", "promotion_type", sa.String(50),
                 server_default="'general_inquiry'")
        _add_col("campaigns", "daily_call_limit", sa.Integer)
        _add_col("campaigns", "calling_hours", sa.String(20),
                 server_default="'09:00-21:00'")
        _add_col("campaigns", "language", sa.String(30), server_default="'english'")
        _add_col("campaigns", "total_leads", sa.Integer, nullable=False,
                 server_default="0")
        _add_col("campaigns", "leads_called", sa.Integer, nullable=False,
                 server_default="0")
        _add_col("campaigns", "leads_interested", sa.Integer, nullable=False,
                 server_default="0")
        _add_col("campaigns", "leads_converted", sa.Integer, nullable=False,
                 server_default="0")
        _add_col("campaigns", "internal_notes", sa.Text)
        _add_col("campaigns", "is_active", sa.Boolean, server_default="true")
        _add_col("campaigns", "deleted_at", sa.TIMESTAMP)

    _add_index("ix_campaigns_dealership_id", "campaigns", "dealership_id")
    _add_index("ix_campaigns_car_model_id", "campaigns", "car_model_id")
    _add_index("ix_campaigns_status", "campaigns", "status")

    # ══════════════════════════════════════════════════════════════════════════
    # leads
    # ══════════════════════════════════════════════════════════════════════════

    if not _table_exists("leads"):
        op.create_table(
            "leads",
            sa.Column("lead_id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("dealership_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("dealerships.dealership_id"), nullable=False),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("campaigns.campaign_id"), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("phone", sa.String(20), nullable=False),
            sa.Column("alternate_phone", sa.String(20), nullable=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("car_interest", sa.String(150), nullable=True),
            sa.Column("variant_preference", sa.String(100), nullable=True),
            sa.Column("fuel_preference", sa.String(30), nullable=True),
            sa.Column("budget_min", sa.Numeric(12, 2), nullable=True),
            sa.Column("budget_max", sa.Numeric(12, 2), nullable=True),
            sa.Column("emi_preferred", sa.Boolean, nullable=True),
            sa.Column("current_car", sa.String(150), nullable=True),
            sa.Column("wants_exchange", sa.Boolean, nullable=True),
            sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
            sa.Column("source_detail", sa.String(255), nullable=True),
            sa.Column("call_status", sa.String(30), nullable=False, server_default="new"),
            sa.Column("interest_level", sa.String(20), nullable=True),
            sa.Column("call_attempts", sa.Integer, nullable=False, server_default="0"),
            sa.Column("last_called_at", sa.TIMESTAMP, nullable=True),
            sa.Column("next_followup_at", sa.TIMESTAMP, nullable=True),
            sa.Column("do_not_call", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("call_summary", sa.Text, nullable=True),
            sa.Column("agent_notes", sa.Text, nullable=True),
            sa.Column("duplicate_of", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("leads.lead_id"), nullable=True),
            sa.Column("is_duplicate", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("added_by", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.user_id"), nullable=True),
            sa.Column("created_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
            sa.Column("deleted_at", sa.TIMESTAMP, nullable=True),
        )
    else:
        # Upgrade existing stub table
        _add_col("leads", "dealership_id", postgresql.UUID(as_uuid=True))
        _add_col("leads", "alternate_phone", sa.String(20))
        _add_col("leads", "email", sa.String(255))
        _add_col("leads", "car_interest", sa.String(150))
        _add_col("leads", "variant_preference", sa.String(100))
        _add_col("leads", "fuel_preference", sa.String(30))
        _add_col("leads", "budget_min", sa.Numeric(12, 2))
        _add_col("leads", "budget_max", sa.Numeric(12, 2))
        _add_col("leads", "emi_preferred", sa.Boolean)
        _add_col("leads", "wants_exchange", sa.Boolean)
        _add_col("leads", "source", sa.String(50), server_default="'manual'")
        _add_col("leads", "source_detail", sa.String(255))
        _add_col("leads", "call_status", sa.String(30), server_default="'new'")
        _add_col("leads", "call_attempts", sa.Integer, server_default="0")
        _add_col("leads", "last_called_at", sa.TIMESTAMP)
        _add_col("leads", "next_followup_at", sa.TIMESTAMP)
        _add_col("leads", "do_not_call", sa.Boolean, server_default="false")
        _add_col("leads", "call_summary", sa.Text)
        _add_col("leads", "agent_notes", sa.Text)
        _add_col("leads", "duplicate_of", postgresql.UUID(as_uuid=True))
        _add_col("leads", "is_duplicate", sa.Boolean, server_default="false")
        _add_col("leads", "added_by", postgresql.UUID(as_uuid=True))
        _add_col("leads", "deleted_at", sa.TIMESTAMP)

    _add_index("ix_leads_dealership_id", "leads", "dealership_id")
    _add_index("ix_leads_campaign_id", "leads", "campaign_id")
    _add_index("ix_leads_phone", "leads", "phone")
    _add_index("ix_leads_call_status", "leads", "call_status")

    # ══════════════════════════════════════════════════════════════════════════
    # campaign_documents
    # ══════════════════════════════════════════════════════════════════════════

    if not _table_exists("campaign_documents"):
        op.create_table(
            "campaign_documents",
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("campaigns.campaign_id"), primary_key=True),
            sa.Column("document_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("documents.document_id"), primary_key=True),
            sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("link_source", sa.String(20), nullable=False, server_default="manual"),
            sa.Column("linked_at", sa.TIMESTAMP, nullable=False,
                      server_default=sa.text("NOW()")),
            sa.Column("linked_by", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("users.user_id"), nullable=True),
        )
    else:
        # Upgrade stub table
        _add_col("campaign_documents", "is_primary", sa.Boolean, server_default="false")
        _add_col("campaign_documents", "link_source", sa.String(20), server_default="'manual'")
        _add_col("campaign_documents", "linked_at", sa.TIMESTAMP,
                 server_default="NOW()")
        _add_col("campaign_documents", "linked_by", postgresql.UUID(as_uuid=True))


def downgrade() -> None:
    op.drop_table("campaign_documents")
    op.drop_table("leads")
    op.drop_table("campaigns")