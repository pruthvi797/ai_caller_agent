"""
Call Model — Day 6
==================

Real-world business context:
  When a campaign is active, the call engine picks leads one by one and
  initiates outbound calls via ElevenLabs + Twilio. Each call attempt
  is stored here with full lifecycle tracking.

  Call lifecycle:
    queued → initiated → in_progress → completed | failed | no_answer | busy | cancelled

  Outcomes (set after call ends, parsed from transcript):
    interested        — customer wants test drive / more info
    not_interested    — explicitly declined
    callback_requested — wants to be called later
    no_answer         — phone rang but no pickup
    voicemail         — went to voicemail
    wrong_number      — wrong person / number
    do_not_call       — requested not to be contacted

  Buying signals (parsed from transcript AI analysis):
    test_drive_requested, pricing_asked, variant_asked,
    exchange_enquired, emi_enquired, competing_model_mentioned
"""

import uuid
from sqlalchemy import (
    Column, String, Integer, TIMESTAMP, ForeignKey,
    Text, Boolean, Numeric, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Call(Base):
    __tablename__ = "calls"

    call_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ─────────────────────────────────────────────────────────────
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.campaign_id"),
        nullable=False,
        index=True
    )
    lead_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leads.lead_id"),
        nullable=False,
        index=True
    )

    # ── ElevenLabs tracking ───────────────────────────────────────────────────
    # The ElevenLabs agent used for this call
    elevenlabs_agent_id = Column(String(255), nullable=True)
    # ElevenLabs conversation_id returned by /v1/convai/twilio/outbound-call
    # Used to fetch transcript: GET /v1/convai/conversations/{conversation_id}
    conversation_id = Column(String(255), nullable=True, index=True, unique=True)

    # ── Phone number called ───────────────────────────────────────────────────
    phone_number = Column(String(20), nullable=False)   # E.164 format

    # ── Call lifecycle status ─────────────────────────────────────────────────
    # queued | initiated | in_progress | completed | failed | no_answer | busy | cancelled
    call_status = Column(String(30), nullable=False, default="queued", index=True)

    # ── Call outcome (set after call ends) ────────────────────────────────────
    # interested | not_interested | callback_requested | no_answer |
    # voicemail | wrong_number | do_not_call | unknown
    call_outcome = Column(String(50), nullable=True)

    # ── Timing ────────────────────────────────────────────────────────────────
    call_duration_seconds = Column(Integer, nullable=True)    # total seconds
    initiated_at = Column(TIMESTAMP, nullable=True)           # when EL accepted the call
    connected_at = Column(TIMESTAMP, nullable=True)           # when customer answered
    ended_at = Column(TIMESTAMP, nullable=True)               # when call ended

    # ── Transcript & Recording ────────────────────────────────────────────────
    transcript = Column(Text, nullable=True)                  # full conversation text
    transcript_json = Column(JSON, nullable=True)             # structured turn-by-turn JSON
    call_recording_url = Column(String(500), nullable=True)   # ElevenLabs recording URL

    # ── AI-parsed buying signals ──────────────────────────────────────────────
    # Set after transcript analysis
    interest_score = Column(Integer, nullable=True)           # 0-10 AI-assigned score
    test_drive_requested = Column(Boolean, nullable=True, default=False)
    pricing_asked = Column(Boolean, nullable=True, default=False)
    variant_asked = Column(Boolean, nullable=True, default=False)
    exchange_enquired = Column(Boolean, nullable=True, default=False)
    emi_enquired = Column(Boolean, nullable=True, default=False)
    competing_model_mentioned = Column(String(150), nullable=True)

    # ── AI call summary ───────────────────────────────────────────────────────
    # Short paragraph summary generated from transcript
    ai_summary = Column(Text, nullable=True)

    # ── Error tracking ────────────────────────────────────────────────────────
    error_message = Column(Text, nullable=True)               # if call_status = failed

    # ── Retry tracking ────────────────────────────────────────────────────────
    attempt_number = Column(Integer, nullable=False, default=1)  # 1, 2, 3...
    # scheduled_at: when this call should be made (for retries / follow-ups)
    scheduled_at = Column(TIMESTAMP, nullable=True)

    # ── Webhook ───────────────────────────────────────────────────────────────
    # Raw webhook payload from ElevenLabs (for debugging)
    webhook_payload = Column(JSON, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    initiated_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=True   # null = triggered by automated engine
    )
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
