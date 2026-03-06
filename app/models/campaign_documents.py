"""
CampaignDocument Model
======================

Links campaigns to their source documents.

Real-world logic:
  When a dealership runs a "March Brezza Campaign", they link:
    1. brezza_brochure.pdf         → brochure
    2. march_2026_pricing.pdf      → pricing_sheet
    3. navratri_exchange_offer.jpg → promotional_offer
    4. brezza_feature_list.docx    → feature_comparison

  The AI agent uses these documents (via the compiled KB) to answer calls.
  A campaign can link documents from multiple car models if it's a multi-model campaign.

  is_primary = True means this is the "main" document — shown first in the
  agent's context window if token limits apply.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, ForeignKey, Boolean, TIMESTAMP, String
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CampaignDocument(Base):
    __tablename__ = "campaign_documents"

    # Composite PK
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.campaign_id"),
        primary_key=True
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.document_id"),
        primary_key=True
    )

    # ── Linking metadata ──────────────────────────────────────────────────────
    # Is this the primary reference document for the campaign?
    is_primary = Column(Boolean, nullable=False, default=False)

    # Why was this doc linked? (auto-linked by system or manually by user)
    # auto | manual
    link_source = Column(String(20), nullable=False, default="manual")

    # ── Audit ─────────────────────────────────────────────────────────────────
    linked_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    linked_by = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)