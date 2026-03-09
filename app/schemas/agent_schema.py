"""
Agent Configuration Schemas — Day 5
=====================================

Pydantic models for request/response validation of the
Agent Configuration and ElevenLabs sync endpoints.
"""

from pydantic import BaseModel, validator, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


# ── Voice options (ElevenLabs built-in voice IDs) ─────────────────────────────
VALID_VOICES = {
    "cgSgspJ2msm6clMCkdW9": "Jessica",
    "pNInz6obpgDQGcFmaJgB": "Adam",
    "9BWtsMINqrJLrRacOk9x": "Aria",
    "CwhRBWXzGAHq8TQ4Fs17": "Roger",
    "EXAVITQu4vr4xnSDxMaL": "Sarah",
}

VALID_LANGUAGES = {"en", "hi", "te", "ta", "kn", "mr", "bn"}

AGENT_STATUSES = {"draft", "configured", "ready", "error"}


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class AgentConfigCreate(BaseModel):
    """
    Create/configure an ElevenLabs agent for a campaign.

    If system_prompt is not provided, a default Suzuki sales prompt is
    auto-generated based on the campaign's car model and promotion type.
    """
    # Voice — either a known name ("Jessica") or raw ElevenLabs voice_id
    voice_id: Optional[str] = "cgSgspJ2msm6clMCkdW9"
    voice_name: Optional[str] = "Jessica"

    # Prompt — if None, auto-generated from campaign details
    system_prompt: Optional[str] = None
    first_message: Optional[str] = None

    # Call language
    language: Optional[str] = "en"

    # Conversation settings
    max_call_duration_secs: Optional[int] = Field(300, ge=60, le=1800)  # 1-30 min
    stability: Optional[float] = Field(0.5, ge=0.0, le=1.0)
    similarity_boost: Optional[float] = Field(0.75, ge=0.0, le=1.0)

    # Which KB to sync to ElevenLabs (must be in "ready" status)
    knowledge_base_id: Optional[UUID] = None

    @validator("language")
    def validate_language(cls, v):
        if v and v not in VALID_LANGUAGES:
            raise ValueError(
                f"Language '{v}' not supported. Choose from: {', '.join(sorted(VALID_LANGUAGES))}"
            )
        return v


class AgentConfigUpdate(BaseModel):
    """Partial update of agent config. Only provided fields are updated."""
    voice_id: Optional[str] = None
    voice_name: Optional[str] = None
    system_prompt: Optional[str] = None
    first_message: Optional[str] = None
    language: Optional[str] = None
    max_call_duration_secs: Optional[int] = Field(None, ge=60, le=1800)
    stability: Optional[float] = Field(None, ge=0.0, le=1.0)
    similarity_boost: Optional[float] = Field(None, ge=0.0, le=1.0)
    knowledge_base_id: Optional[UUID] = None

    @validator("language")
    def validate_language(cls, v):
        if v and v not in VALID_LANGUAGES:
            raise ValueError(f"Language must be one of: {', '.join(sorted(VALID_LANGUAGES))}")
        return v


class KBSyncRequest(BaseModel):
    """
    Request body for POST /agents/{campaign_id}/sync-kb

    Optionally override which KB to sync (defaults to agent_config.knowledge_base_id).
    """
    knowledge_base_id: Optional[UUID] = None  # override if needed


# ══════════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class AgentConfigResponse(BaseModel):
    """Full agent config response."""
    agent_id: UUID
    campaign_id: UUID
    dealership_id: UUID

    # ElevenLabs
    elevenlabs_agent_id: Optional[str]
    voice_id: str
    voice_name: Optional[str]

    # Prompt
    system_prompt: str
    first_message: Optional[str]

    # KB sync
    knowledge_base_id: Optional[UUID]
    elevenlabs_kb_id: Optional[str]
    kb_synced_at: Optional[datetime]
    kb_sync_status: Optional[str]
    kb_sync_error: Optional[str]

    # Settings
    language: str
    max_call_duration_secs: int
    stability: float
    similarity_boost: float

    # Status
    status: str
    error_message: Optional[str]

    # Audit
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VoiceOption(BaseModel):
    voice_id: str
    name: str
    description: str


class ElevenLabsStatusResponse(BaseModel):
    """Response from GET /agents/elevenlabs-status"""
    connected: bool
    api_key_set: bool
    subscription: Optional[str] = None
    character_count: Optional[int] = None
    character_limit: Optional[int] = None
    error: Optional[str] = None
    available_voices: List[VoiceOption] = []
