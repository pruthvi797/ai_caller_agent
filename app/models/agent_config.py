"""
Agent Configuration Model
==========================

Real-world context:
  Each campaign has exactly ONE ElevenLabs AI agent configuration.
  When a campaign goes active, this config tells the AI agent:
    - What voice to use (Indian English male/female, Hindi accent, etc.)
    - The system prompt (sales personality + what to say)
    - Which ElevenLabs agent ID to use for outbound calls
    - Which knowledge base is synced to ElevenLabs
    - Conversation settings (how long to wait before speaking, etc.)

  ElevenLabs agent lifecycle for this project:
    1. POST /agents/{campaign_id}/configure
         → Create/update ElevenLabs agent via API
         → Store elevenlabs_agent_id in agent_config
    2. POST /agents/{campaign_id}/sync-kb
         → Push compiled KB text to ElevenLabs as a knowledge base document
         → Store elevenlabs_kb_id in agent_config
    3. POST /calls/initiate (Day 6)
         → Use elevenlabs_agent_id to start outbound call via ElevenLabs

  Voice options (ElevenLabs voice IDs for Indian-accent voices):
    - "Rachel"  : Professional female, neutral accent (good default)
    - "Adam"    : Professional male, neutral accent
    - "Custom"  : Dealership can paste any ElevenLabs voice ID

  System prompt strategy:
    Base prompt = Suzuki sales rep personality
    KB content is injected by ElevenLabs automatically from linked knowledge base
"""

import uuid
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Text, Boolean, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class AgentConfig(Base):
    __tablename__ = "agent_config"

    agent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ──────────────────────────────────────────────────────────────
    campaign_id = Column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.campaign_id"),
        nullable=False,
        unique=True,         # one config per campaign
        index=True
    )
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=True
    )

    # ── ElevenLabs Agent ───────────────────────────────────────────────────────
    # Returned by ElevenLabs when agent is created — used for outbound calls
    elevenlabs_agent_id = Column(String(255), nullable=True)

    # ElevenLabs voice ID — use a real ElevenLabs voice_id string
    # Defaults to "Rachel" voice (ElevenLabs built-in)
    voice_id = Column(
        String(255),
        nullable=False,
        default="cgSgspJ2msm6clMCkdW9"   # "Jessica" — clear Indian-friendly accent
    )
    # Human-friendly voice name for UI display
    voice_name = Column(String(100), nullable=True, default="Jessica")

    # ── Prompts ────────────────────────────────────────────────────────────────
    # Main system prompt — defines the agent's personality and role
    system_prompt = Column(Text, nullable=False)

    # First thing the agent says when call connects
    first_message = Column(Text, nullable=True)

    # ── Knowledge Base (ElevenLabs side) ──────────────────────────────────────
    # Our internal KB ID (from knowledge_bases table)
    knowledge_base_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.kb_id"),
        nullable=True
    )
    # ElevenLabs knowledge base document ID — returned after sync
    elevenlabs_kb_id = Column(String(255), nullable=True)
    # When KB was last pushed to ElevenLabs
    kb_synced_at = Column(TIMESTAMP, nullable=True)
    # Status of last KB sync attempt
    kb_sync_status = Column(String(30), nullable=True)  # pending | synced | failed
    kb_sync_error = Column(Text, nullable=True)

    # ── Conversation Settings ──────────────────────────────────────────────────
    # Language: "en" | "hi" | "te" | "ta" | "kn" — ISO 639-1
    language = Column(String(10), nullable=False, default="en")

    # Max call duration in seconds (prevent runaway calls)
    max_call_duration_secs = Column(Integer, nullable=False, default=300)   # 5 min

    # How long agent waits before speaking first (milliseconds)
    stability = Column(Float, nullable=False, default=0.5)       # voice stability
    similarity_boost = Column(Float, nullable=False, default=0.75)  # voice clarity

    # ── Agent Status ───────────────────────────────────────────────────────────
    # draft | configured | ready | error
    # draft      = just created, not pushed to ElevenLabs yet
    # configured = ElevenLabs agent created, no KB synced yet
    # ready      = ElevenLabs agent + KB synced, ready to make calls
    # error      = something went wrong (check error_message)
    status = Column(String(30), nullable=False, default="draft")
    error_message = Column(Text, nullable=True)

    # ── Audit ──────────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
