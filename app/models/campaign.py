"""
Campaign Model
==============

Real-world business context:
  A Suzuki dealership runs campaigns to sell specific car models.
  Each campaign has a promotion type (e.g. Festive Offer, Test Drive Push,
  Exchange Bonus), a target window (start/end date), and a list of leads to call.

  The AI caller agent uses the campaign's linked KB + documents to answer
  customer questions accurately during outbound calls.

  Campaign lifecycle:
    draft → active → paused → completed | cancelled

  Promotion types (real Suzuki dealership use cases):
    - festive_offer      : Diwali / Navratri / year-end offers
    - new_launch         : New model/variant launch push
    - test_drive         : Drive more footfall to showroom
    - exchange_bonus     : Trade-in old car for new Suzuki
    - emi_scheme         : Low EMI / 0% finance push
    - corporate_offer    : Fleet / corporate buyer outreach
    - service_camp       : Existing customer service follow-up
    - general_inquiry    : Catch-all inbound/outbound
"""

import uuid
from sqlalchemy import Column, String, Date, TIMESTAMP, ForeignKey, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ─────────────────────────────────────────────────────────────
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False
    )

    # ── Car model being promoted ──────────────────────────────────────────────
    # One campaign = one car model focus (e.g. "March Brezza Campaign")
    # Null = brand-wide campaign (e.g. "Navratri Offer — All Models")
    car_model_id = Column(
        UUID(as_uuid=True),
        ForeignKey("car_models.car_model_id"),
        nullable=True,
        index=True
    )

    # ── Campaign identity ─────────────────────────────────────────────────────
    campaign_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # festive_offer | new_launch | test_drive | exchange_bonus |
    # emi_scheme | corporate_offer | service_camp | general_inquiry
    promotion_type = Column(String(50), nullable=False, default="general_inquiry")

    # ── Schedule ──────────────────────────────────────────────────────────────
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # ── Status lifecycle ──────────────────────────────────────────────────────
    # draft → active → paused → completed | cancelled
    status = Column(String(20), nullable=False, default="draft")

    # ── Calling configuration ─────────────────────────────────────────────────
    # Which KB the AI agent uses for this campaign's calls
    knowledge_base_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.kb_id"),
        nullable=True
    )
    # Max calls per day for this campaign (rate limiting / agent capacity)
    daily_call_limit = Column(Integer, nullable=True)
    # Calling hours window e.g. "09:00-21:00"
    calling_hours = Column(String(20), nullable=True, default="09:00-21:00")
    # Language for the AI agent: "hindi", "english", "telugu", etc.
    language = Column(String(30), nullable=True, default="english")

    # ── Lead stats (denormalised for fast dashboard queries) ──────────────────
    total_leads = Column(Integer, nullable=False, default=0)
    leads_called = Column(Integer, nullable=False, default=0)
    leads_interested = Column(Integer, nullable=False, default=0)
    leads_converted = Column(Integer, nullable=False, default=0)

    # ── Notes ─────────────────────────────────────────────────────────────────
    internal_notes = Column(Text, nullable=True)   # sales manager notes

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(TIMESTAMP, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)