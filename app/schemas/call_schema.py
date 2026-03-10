"""
Call Schemas — Day 6
"""
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator

CALL_STATUSES = {
    "queued", "initiated", "in_progress",
    "completed", "failed", "no_answer", "busy", "cancelled"
}
CALL_OUTCOMES = {
    "interested", "not_interested", "callback_requested",
    "no_answer", "voicemail", "wrong_number", "do_not_call", "unknown"
}


class InitiateCallRequest(BaseModel):
    campaign_id: uuid.UUID
    lead_id: uuid.UUID
    agent_phone_number_id: Optional[str] = None


class StartCampaignCallsRequest(BaseModel):
    max_leads: Optional[int] = Field(None, ge=1, le=500)
    agent_phone_number_id: Optional[str] = None


class CallStatusUpdateRequest(BaseModel):
    call_status: Optional[str] = None
    call_outcome: Optional[str] = None
    call_duration_seconds: Optional[int] = None
    ai_summary: Optional[str] = None

    @field_validator("call_status")
    @classmethod
    def valid_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CALL_STATUSES:
            raise ValueError(f"call_status must be one of: {', '.join(sorted(CALL_STATUSES))}")
        return v

    @field_validator("call_outcome")
    @classmethod
    def valid_outcome(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CALL_OUTCOMES:
            raise ValueError(f"call_outcome must be one of: {', '.join(sorted(CALL_OUTCOMES))}")
        return v


class CallResponse(BaseModel):
    call_id: uuid.UUID
    dealership_id: uuid.UUID
    campaign_id: uuid.UUID
    lead_id: uuid.UUID
    elevenlabs_agent_id: Optional[str]
    conversation_id: Optional[str]
    phone_number: str
    call_status: str
    call_outcome: Optional[str]
    call_duration_seconds: Optional[int]
    initiated_at: Optional[datetime]
    connected_at: Optional[datetime]
    ended_at: Optional[datetime]
    transcript: Optional[str]
    call_recording_url: Optional[str]
    interest_score: Optional[int]
    test_drive_requested: Optional[bool]
    pricing_asked: Optional[bool]
    variant_asked: Optional[bool]
    exchange_enquired: Optional[bool]
    emi_enquired: Optional[bool]
    competing_model_mentioned: Optional[str]
    ai_summary: Optional[str]
    error_message: Optional[str]
    attempt_number: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class CallDetailResponse(CallResponse):
    transcript_json: Optional[List[Dict[str, Any]]] = None
    lead_name: Optional[str] = None
    lead_phone: Optional[str] = None
    lead_email: Optional[str] = None


class CallInitiateResponse(BaseModel):
    call_id: uuid.UUID
    conversation_id: Optional[str]
    lead_id: uuid.UUID
    phone_number: str
    call_status: str
    message: str


class StartCampaignResponse(BaseModel):
    campaign_id: uuid.UUID
    campaign_name: str
    total_leads_queued: int
    calls_initiated: int
    calls_skipped: int
    skip_reasons: List[Dict[str, str]]
    message: str


class CampaignCallStats(BaseModel):
    campaign_id: uuid.UUID
    campaign_name: str
    promotion_type: str
    total_leads: int
    leads_called: int
    leads_pending: int
    leads_do_not_call: int
    calls_completed: int
    calls_failed: int
    calls_no_answer: int
    calls_busy: int
    calls_in_progress: int
    outcome_interested: int
    outcome_not_interested: int
    outcome_callback_requested: int
    outcome_voicemail: int
    outcome_wrong_number: int
    test_drive_requests: int
    pricing_enquiries: int
    exchange_enquiries: int
    emi_enquiries: int
    connection_rate: float
    interest_rate: float
    avg_call_duration_seconds: Optional[float]
    total_talk_time_seconds: int


class HotLeadSummary(BaseModel):
    lead_id: uuid.UUID
    call_id: uuid.UUID
    name: str
    phone: str
    email: Optional[str]
    car_interest: Optional[str]
    call_outcome: str
    interest_score: Optional[int]
    test_drive_requested: bool
    ai_summary: Optional[str]
    called_at: Optional[datetime]


class CallLogEntry(BaseModel):
    call_id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str
    phone_number: str
    call_status: str
    call_outcome: Optional[str]
    call_duration_seconds: Optional[int]
    interest_score: Optional[int]
    test_drive_requested: Optional[bool]
    ai_summary: Optional[str]
    initiated_at: Optional[datetime]
    ended_at: Optional[datetime]
    attempt_number: int
    model_config = {"from_attributes": True}
