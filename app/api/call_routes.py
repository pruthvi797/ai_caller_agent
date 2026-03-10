import logging
"""
Call Routes — Day 6
====================

Task 6.1 — Call Initiation
  POST /calls/initiate                          Single lead call
  POST /calls/campaign/{campaign_id}/start      Batch campaign calls

Task 6.2 — Call Response Tracking
  POST /calls/webhook                           ElevenLabs webhook receiver
  GET  /calls/{call_id}                         Call detail
  GET  /calls/{call_id}/transcript              Fetch transcript (polls EL if missing)
  PATCH /calls/{call_id}                        Manual update

Task 6.3 — Call Analytics
  GET  /calls/campaign/{campaign_id}            Paginated call log
  GET  /calls/campaign/{campaign_id}/stats      Aggregate statistics
  GET  /calls/campaign/{campaign_id}/hot-leads  High interest leads

Pylance fix notes:
  - SQLAlchemy Column attributes used in `if` → compare to None explicitly or cast
  - Column values passed to Pydantic → use type: ignore[arg-type]
  - `campaign_id` variable scoping fixed in initiate endpoint
"""

import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.call import Call
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.models.agent_config import AgentConfig
from app.models.user import User
from app.schemas.call_schema import (
    InitiateCallRequest,
    StartCampaignCallsRequest,
    CallStatusUpdateRequest,
    CallResponse,
    CallDetailResponse,
    CallInitiateResponse,
    StartCampaignResponse,
    CampaignCallStats,
    HotLeadSummary,
    CallLogEntry,
)
from app.services.call_engine import (
    initiate_single_call,
    start_campaign_calls,
    process_webhook_event,
    fetch_and_store_transcript,
    get_campaign_call_stats,
    get_hot_leads,
    get_call_logs,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calls", tags=["Call Engine"])


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _require_dealership(current_user: User) -> None:
    # FIX: current_user.dealership_id is Column[UUID] — compare to None explicitly
    if current_user.dealership_id is None:
        raise HTTPException(
            status_code=400,
            detail="You must create a dealership first (POST /dealership/create)"
        )


def _get_campaign_or_404(campaign_id: str, dealership_id: object, db: Session) -> Campaign:
    c = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id,
        Campaign.dealership_id == dealership_id,
        Campaign.deleted_at.is_(None),
    ).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


def _get_call_or_404(call_id: str, dealership_id: object, db: Session) -> Call:
    call = db.query(Call).filter(
        Call.call_id == call_id,
        Call.dealership_id == dealership_id,
    ).first()
    if call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return call


# ══════════════════════════════════════════════════════════════════════════════
# TASK 6.1 — CALL INITIATION
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/initiate", response_model=CallInitiateResponse, status_code=201)
def initiate_call(
    body: InitiateCallRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Initiate a single outbound call to one lead.

    Prerequisites:
      - Campaign must be active
      - Lead must belong to campaign and not be on DNC
      - Agent must be configured with status = ready
      - ELEVENLABS_PHONE_NUMBER_ID must be set in .env
    """
    _require_dealership(current_user)

    # FIX: body.campaign_id is a UUID object — convert to str for query helper
    campaign_id_str = str(body.campaign_id)
    campaign = _get_campaign_or_404(campaign_id_str, current_user.dealership_id, db)

    # FIX: campaign.status is Column[str] — cast to str before comparing
    if str(campaign.status) != "active":
        raise HTTPException(
            status_code=422,
            detail=f"Campaign status is '{campaign.status}'. Only active campaigns can initiate calls."
        )

    lead = db.query(Lead).filter(
        Lead.lead_id == body.lead_id,
        Lead.campaign_id == body.campaign_id,
        Lead.deleted_at.is_(None),
    ).first()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found in this campaign")

    # FIX: lead.do_not_call is Column[bool] — use bool() cast
    if bool(lead.do_not_call):
        raise HTTPException(status_code=422, detail="Lead is on the Do Not Call list")

    agent_config = db.query(AgentConfig).filter(
        AgentConfig.campaign_id == body.campaign_id
    ).first()
    if agent_config is None:
        raise HTTPException(
            status_code=422,
            detail=f"No agent configured for campaign {campaign_id_str}. "
                   "Run POST /agents/{campaign_id}/configure first."
        )
    # FIX: agent_config.status is Column[str] — cast before comparing
    if str(agent_config.status) != "ready":
        raise HTTPException(
            status_code=422,
            detail=f"Agent status is '{agent_config.status}'. Must be 'ready'. "
                   f"Run POST /agents/{campaign_id_str}/sync-kb first."
        )

    try:
        call = initiate_single_call(
            lead=lead,
            campaign=campaign,
            agent_config=agent_config,
            db=db,
            agent_phone_number_id=body.agent_phone_number_id,
            initiated_by_user_id=current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Call initiation failed: {str(e)}")

    return CallInitiateResponse(
        call_id=call.call_id,           # type: ignore[arg-type]
        conversation_id=str(call.conversation_id) if call.conversation_id is not None else None,
        lead_id=lead.lead_id,           # type: ignore[arg-type]
        phone_number=str(lead.phone),
        call_status=str(call.call_status),
        message=(
            f"Call initiated to {lead.name} ({lead.phone}). "
            f"Conversation ID: {call.conversation_id}"
        ),
    )


@router.post("/campaign/{campaign_id}/start", response_model=StartCampaignResponse, status_code=201)
def start_campaign(
    campaign_id: str,
    body: StartCampaignCallsRequest = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start the call engine for an entire campaign batch.

    Picks all eligible new leads (call_status=new, not DNC, not duplicate)
    and initiates AI outbound calls via ElevenLabs.
    Respects campaign.daily_call_limit and body.max_leads override.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    if str(campaign.status) != "active":
        raise HTTPException(
            status_code=422,
            detail=f"Campaign is '{campaign.status}'. Only active campaigns can start calls."
        )

    try:
        result = start_campaign_calls(
            campaign=campaign,
            db=db,
            request=body,
            initiated_by_user_id=current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Campaign call engine error: {str(e)}")

    return StartCampaignResponse(**result)


# ══════════════════════════════════════════════════════════════════════════════
# TASK 6.2 — CALL RESPONSE TRACKING
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/webhook", status_code=200)
async def elevenlabs_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    ElevenLabs webhook receiver - no authentication required.
    Always returns 200 so ElevenLabs does not retry endlessly.
    """
    # Read raw body first for logging regardless of format
    raw_body = await request.body()
    logger.info(f"Webhook received. Body: {raw_body.decode('utf-8', errors='replace')[:1000]}")
    logger.info(f"Webhook content-type: {request.headers.get('content-type', 'none')}")

    # Try JSON parse - ElevenLabs sometimes sends non-JSON pings
    try:
        payload = await request.json()
    except Exception:
        logger.warning(f"Webhook non-JSON body: {raw_body[:200]}")
        return {"status": "ok", "message": "received"}

    logger.info(f"Webhook event type: {payload.get('type', 'unknown')}")

    try:
        call = process_webhook_event(payload, db)
    except Exception as e:
        # Never return 4xx/5xx to ElevenLabs - it will retry endlessly
        logger.error(f"Webhook processing error: {e}")
        return {"status": "error", "message": str(e)}

    if call is not None:
        return {
            "status": "processed",
            "call_id": str(call.call_id),
            "call_status": str(call.call_status),
        }

    return {"status": "ignored", "message": "Event not handled or unknown conversation_id"}


@router.get("/{call_id}", response_model=CallDetailResponse)
def get_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full details of a single call including transcript and buying signals."""
    _require_dealership(current_user)
    call = _get_call_or_404(call_id, current_user.dealership_id, db)

    lead = db.query(Lead).filter(Lead.lead_id == call.lead_id).first()

    result = CallDetailResponse.model_validate(call)
    if lead is not None:
        result.lead_name = str(lead.name)
        result.lead_phone = str(lead.phone)
        result.lead_email = str(lead.email) if lead.email is not None else None

    return result


@router.get("/{call_id}/transcript", response_model=CallDetailResponse)
def get_call_transcript(
    call_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get call transcript. If missing, polls ElevenLabs to fetch it.

    Fallback for cases where the webhook was missed (server downtime, etc).
    """
    _require_dealership(current_user)
    call = _get_call_or_404(call_id, current_user.dealership_id, db)

    # FIX: all Column comparisons use is None / is not None or explicit str/bool casts
    transcript_missing = call.transcript is None or str(call.transcript) == ""
    has_conversation_id = call.conversation_id is not None
    status_allows_fetch = str(call.call_status) in ("completed", "in_progress")

    if transcript_missing and has_conversation_id and status_allows_fetch:
        try:
            call = fetch_and_store_transcript(call, db)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Could not fetch transcript from ElevenLabs: {str(e)}"
            )
    elif not has_conversation_id:
        raise HTTPException(
            status_code=422,
            detail="No conversation_id on this call — transcript unavailable"
        )

    lead = db.query(Lead).filter(Lead.lead_id == call.lead_id).first()

    result = CallDetailResponse.model_validate(call)
    if lead is not None:
        result.lead_name = str(lead.name)
        result.lead_phone = str(lead.phone)
        result.lead_email = str(lead.email) if lead.email is not None else None

    return result


@router.patch("/{call_id}", response_model=CallResponse)
def update_call(
    call_id: str,
    body: CallStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually update a call record.
    Used for corrections or testing (e.g. marking a test call as completed).
    """
    _require_dealership(current_user)
    call = _get_call_or_404(call_id, current_user.dealership_id, db)

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    for field, value in update_data.items():
        setattr(call, field, value)
    call.updated_at = datetime.utcnow()  # type: ignore[assignment]

    db.commit()
    db.refresh(call)
    return call


# ══════════════════════════════════════════════════════════════════════════════
# TASK 6.3 — CALL ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/campaign/{campaign_id}", response_model=List[CallLogEntry])
def list_campaign_calls(
    campaign_id: str,
    call_status: Optional[str] = Query(
        None,
        description="Filter by status: queued|initiated|in_progress|completed|failed|no_answer|busy|cancelled"
    ),
    call_outcome: Optional[str] = Query(
        None,
        description="Filter by outcome: interested|not_interested|callback_requested|no_answer|voicemail|wrong_number|do_not_call|unknown"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Paginated call log for a campaign.
    Shown in the Call Logs UI — every attempt with status, outcome, duration, score.
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    return get_call_logs(
        campaign_id=campaign_id,
        db=db,
        call_status=call_status,
        call_outcome=call_outcome,
        skip=skip,
        limit=limit,
    )


@router.get("/campaign/{campaign_id}/stats", response_model=CampaignCallStats)
def campaign_call_stats(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Aggregate call statistics for the campaign dashboard.

    Returns totals, connection rate, interest rate, buying signal breakdown,
    and average call duration — used to render KPI cards and charts.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    return get_campaign_call_stats(campaign, db)


@router.get("/campaign/{campaign_id}/hot-leads", response_model=List[HotLeadSummary])
def campaign_hot_leads(
    campaign_id: str,
    min_score: int = Query(6, ge=0, le=10, description="Minimum interest score (0-10)"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Hot leads — sorted by interest_score descending.
    Shown to sales manager every morning for immediate human follow-up.
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    return get_hot_leads(
        campaign_id=campaign_id,
        db=db,
        min_score=min_score,
        limit=limit,
    )