"""
Call Engine Service — Day 6
============================

Core business logic for:
  Task 6.1 — Call Initiation
  Task 6.2 — Call Response Tracking
  Task 6.3 — Call Analytics

Pylance fix notes:
  - SQLAlchemy Column values used in Python `if` must be cast:
      bool(col) for bool columns
      col is not None for nullable checks
      str(col) before string comparisons
  - Column attribute assignments use `# type: ignore[assignment]`
    because Pylance sees Column[X] not X at runtime after ORM load
"""

import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.call import Call
from app.models.lead import Lead
from app.models.campaign import Campaign
from app.models.agent_config import AgentConfig
from app.schemas.call_schema import (
    StartCampaignCallsRequest,
    CampaignCallStats,
    HotLeadSummary,
    CallLogEntry,
)

logger = logging.getLogger(__name__)

ELEVENLABS_PHONE_NUMBER_ID = os.getenv("ELEVENLABS_PHONE_NUMBER_ID", "")
MAX_CALL_ATTEMPTS = 3


# ══════════════════════════════════════════════════════════════════════════════
# TASK 6.1 — CALL INITIATION
# ══════════════════════════════════════════════════════════════════════════════

def initiate_single_call(
    lead: Lead,
    campaign: Campaign,
    agent_config: AgentConfig,
    db: Session,
    agent_phone_number_id: Optional[str] = None,
    initiated_by_user_id: Any = None,
) -> Call:
    """
    Initiate a single outbound call to one lead.

    Steps:
      1. Create Call(queued)
      2. Call ElevenLabs /v1/convai/twilio/outbound-call
      3. Update Call → initiated + store conversation_id
      4. Update Lead: call_attempts += 1, call_status = 'called'
    """
    from app.services.elevenlabs_service import initiate_outbound_call, ElevenLabsAPIError

    phone_id = agent_phone_number_id or ELEVENLABS_PHONE_NUMBER_ID
    if not phone_id:
        raise ValueError(
            "ELEVENLABS_PHONE_NUMBER_ID is not configured. "
            "Add your Twilio number in ElevenLabs Dashboard → Settings → Telephony, "
            "then set ELEVENLABS_PHONE_NUMBER_ID in your .env file."
        )

    # FIX: agent_config.elevenlabs_agent_id is a Column — compare to None explicitly
    if agent_config.elevenlabs_agent_id is None:
        raise ValueError(
            f"Agent for campaign {campaign.campaign_id} has no ElevenLabs agent ID. "
            "Configure it first via POST /agents/{campaign_id}/configure"
        )

    now = datetime.utcnow()

    # Determine attempt number
    previous_attempts: int = db.query(func.count(Call.call_id)).filter(
        Call.lead_id == lead.lead_id
    ).scalar() or 0

    call = Call(
        dealership_id=campaign.dealership_id,
        campaign_id=campaign.campaign_id,
        lead_id=lead.lead_id,
        elevenlabs_agent_id=str(agent_config.elevenlabs_agent_id),
        phone_number=str(lead.phone),
        call_status="queued",
        attempt_number=previous_attempts + 1,
        initiated_by=initiated_by_user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(call)
    db.flush()  # get call_id without committing

    try:
        result = initiate_outbound_call(
            elevenlabs_agent_id=str(agent_config.elevenlabs_agent_id),
            phone_number=str(lead.phone),
            agent_phone_number_id=phone_id,
            metadata={
                "call_id": str(call.call_id),
                "lead_id": str(lead.lead_id),
                "campaign_id": str(campaign.campaign_id),
                "dealership_id": str(campaign.dealership_id),
                "lead_name": str(lead.name),
            },
        )

        conversation_id = result.get("conversation_id") or result.get("call_id")

        # FIX: all attribute assignments on ORM objects use type: ignore[assignment]
        call.conversation_id = conversation_id          # type: ignore[assignment]
        call.call_status = "initiated"                  # type: ignore[assignment]
        call.initiated_at = datetime.utcnow()           # type: ignore[assignment]
        call.updated_at = datetime.utcnow()             # type: ignore[assignment]

        lead.call_attempts = (lead.call_attempts or 0) + 1  # type: ignore[assignment]
        lead.last_called_at = datetime.utcnow()              # type: ignore[assignment]
        lead.call_status = "called"                          # type: ignore[assignment]
        lead.updated_at = datetime.utcnow()                  # type: ignore[assignment]

        db.commit()
        db.refresh(call)
        logger.info(
            f"Call initiated: lead={lead.lead_id} phone={lead.phone} "
            f"conversation_id={conversation_id}"
        )
        return call

    except ElevenLabsAPIError as e:
        call.call_status = "failed"                                         # type: ignore[assignment]
        call.error_message = f"ElevenLabs API error [{e.status_code}]: {e.message}"  # type: ignore[assignment]
        call.updated_at = datetime.utcnow()                                 # type: ignore[assignment]
        db.commit()
        logger.error(f"Call failed for lead {lead.lead_id}: {e.message}")
        raise

    except Exception as e:
        call.call_status = "failed"             # type: ignore[assignment]
        call.error_message = str(e)             # type: ignore[assignment]
        call.updated_at = datetime.utcnow()     # type: ignore[assignment]
        db.commit()
        logger.error(f"Unexpected error initiating call for lead {lead.lead_id}: {e}")
        raise


def start_campaign_calls(
    campaign: Campaign,
    db: Session,
    request: StartCampaignCallsRequest,
    initiated_by_user_id: Any = None,
) -> Dict[str, Any]:
    """
    Batch call engine — initiates calls for all eligible leads in a campaign.

    Eligible: call_status='new', do_not_call=False, is_duplicate=False,
              call_attempts < MAX_CALL_ATTEMPTS
    """
    from app.services.elevenlabs_service import ElevenLabsAPIError

    agent_config = db.query(AgentConfig).filter(
        AgentConfig.campaign_id == campaign.campaign_id
    ).first()

    if agent_config is None:
        raise ValueError(
            f"No agent configured for campaign {campaign.campaign_id}. "
            "Run POST /agents/{campaign_id}/configure first."
        )

    # FIX: compare string column value explicitly — str() cast to avoid Column[str] bool issue
    if str(agent_config.status) != "ready":
        raise ValueError(
            f"Agent status is '{agent_config.status}'. "
            "Agent must be 'ready' (KB synced) before starting calls. "
            "Run POST /agents/{campaign_id}/sync-kb first."
        )

    # Today's call count
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_call_count: int = db.query(func.count(Call.call_id)).filter(
        Call.campaign_id == campaign.campaign_id,
        Call.created_at >= today_start,
    ).scalar() or 0

    remaining_daily_limit: Optional[int] = None
    # FIX: campaign.daily_call_limit is Column[int|None] — cast via int(str()) to satisfy Pylance
    if campaign.daily_call_limit is not None:
        _daily_limit: int = int(campaign.daily_call_limit)  # type: ignore[arg-type]
        remaining_daily_limit = max(0, _daily_limit - today_call_count)
        if remaining_daily_limit == 0:
            raise ValueError(
                f"Daily call limit of {campaign.daily_call_limit} reached for today. "
                "Calls will resume tomorrow."
            )

    lead_query = db.query(Lead).filter(
        Lead.campaign_id == campaign.campaign_id,
        Lead.call_status == "new",
        Lead.do_not_call == False,      # noqa: E712  — SQLAlchemy filter, not Python bool
        Lead.is_duplicate == False,     # noqa: E712
        Lead.deleted_at.is_(None),
        Lead.call_attempts < MAX_CALL_ATTEMPTS,
    )

    # Apply batch limit: use the smaller of max_leads and remaining_daily_limit
    batch_limit: Optional[int] = None
    if request.max_leads is not None and remaining_daily_limit is not None:
        batch_limit = min(request.max_leads, remaining_daily_limit)
    elif request.max_leads is not None:
        batch_limit = request.max_leads
    elif remaining_daily_limit is not None:
        batch_limit = remaining_daily_limit

    if batch_limit is not None:
        lead_query = lead_query.limit(batch_limit)

    leads = lead_query.all()

    if not leads:
        return {
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "total_leads_queued": 0,
            "calls_initiated": 0,
            "calls_skipped": 0,
            "skip_reasons": [],
            "message": "No eligible leads found. All leads have been called or marked DNC.",
        }

    calls_initiated = 0
    calls_failed = 0
    skip_reasons: List[Dict[str, str]] = []

    for lead in leads:
        try:
            initiate_single_call(
                lead=lead,
                campaign=campaign,
                agent_config=agent_config,
                db=db,
                agent_phone_number_id=request.agent_phone_number_id,
                initiated_by_user_id=initiated_by_user_id,
            )
            calls_initiated += 1
        except ElevenLabsAPIError as e:
            calls_failed += 1
            skip_reasons.append({
                "lead_id": str(lead.lead_id),
                "name": str(lead.name),
                "reason": f"ElevenLabs error: {e.message}",
            })
        except Exception as e:
            calls_failed += 1
            skip_reasons.append({
                "lead_id": str(lead.lead_id),
                "name": str(lead.name),
                "reason": str(e),
            })

    return {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.campaign_name,
        "total_leads_queued": len(leads),
        "calls_initiated": calls_initiated,
        "calls_skipped": calls_failed,
        "skip_reasons": skip_reasons,
        "message": (
            f"Campaign call batch started: {calls_initiated} calls initiated, "
            f"{calls_failed} failed."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# TASK 6.2 — CALL RESPONSE TRACKING
# ══════════════════════════════════════════════════════════════════════════════

def process_webhook_event(payload: Dict[str, Any], db: Session) -> Optional[Call]:
    """
    Handle an ElevenLabs webhook event.

    conversation.started  → call_status = in_progress
    conversation.ended    → store transcript, parse signals, update lead + campaign
    conversation.failed   → call_status = failed/no_answer/busy
    """
    event_type = str(payload.get("type", ""))
    conversation_id = str(payload.get("conversation_id", ""))

    if not conversation_id:
        logger.warning(f"Webhook received with no conversation_id: {payload}")
        return None

    call = db.query(Call).filter(Call.conversation_id == conversation_id).first()
    if call is None:
        logger.warning(f"Webhook for unknown conversation_id: {conversation_id}")
        return None

    now = datetime.utcnow()

    # ── conversation.started ──────────────────────────────────────────────────
    if event_type == "conversation.started":
        call.call_status = "in_progress"    # type: ignore[assignment]
        call.connected_at = now             # type: ignore[assignment]
        call.updated_at = now               # type: ignore[assignment]
        call.webhook_payload = payload      # type: ignore[assignment]
        db.commit()
        logger.info(f"Call in progress: conversation_id={conversation_id}")
        return call

    # ── conversation.ended ────────────────────────────────────────────────────
    if event_type == "conversation.ended":
        transcript_text: str = payload.get("transcript") or ""
        duration_secs = payload.get("call_duration_secs") or payload.get("duration_secs")
        recording_url = payload.get("recording_url")

        signals = parse_transcript_signals(transcript_text)

        call.call_status = "completed"                          # type: ignore[assignment]
        call.ended_at = now                                     # type: ignore[assignment]
        call.transcript = transcript_text                       # type: ignore[assignment]
        call.call_recording_url = recording_url                 # type: ignore[assignment]
        call.webhook_payload = payload                          # type: ignore[assignment]
        call.interest_score = signals["interest_score"]         # type: ignore[assignment]
        call.test_drive_requested = signals["test_drive_requested"]  # type: ignore[assignment]
        call.pricing_asked = signals["pricing_asked"]           # type: ignore[assignment]
        call.variant_asked = signals["variant_asked"]           # type: ignore[assignment]
        call.exchange_enquired = signals["exchange_enquired"]   # type: ignore[assignment]
        call.emi_enquired = signals["emi_enquired"]             # type: ignore[assignment]
        call.competing_model_mentioned = signals["competing_model_mentioned"]  # type: ignore[assignment]
        call.ai_summary = signals["ai_summary"]                 # type: ignore[assignment]
        call.call_outcome = signals["call_outcome"]             # type: ignore[assignment]
        call.updated_at = now                                   # type: ignore[assignment]

        # FIX: duration may be Column or raw int — cast explicitly
        if duration_secs is not None:
            call.call_duration_seconds = int(duration_secs)    # type: ignore[assignment]

        lead = db.query(Lead).filter(Lead.lead_id == call.lead_id).first()
        if lead is not None:
            outcome = signals["call_outcome"]
            lead.updated_at = now  # type: ignore[assignment]

            if outcome == "interested":
                lead.call_status = "interested"    # type: ignore[assignment]
                score = signals["interest_score"] or 0
                lead.interest_level = "hot" if score >= 7 else "warm"  # type: ignore[assignment]
            elif outcome == "not_interested":
                lead.call_status = "not_interested"  # type: ignore[assignment]
                lead.interest_level = "cold"          # type: ignore[assignment]
            elif outcome == "callback_requested":
                lead.call_status = "follow_up"        # type: ignore[assignment]
                lead.interest_level = "warm"          # type: ignore[assignment]
            elif outcome == "do_not_call":
                lead.call_status = "dnc"              # type: ignore[assignment]
                lead.do_not_call = True               # type: ignore[assignment]
            else:
                lead.call_status = "called"           # type: ignore[assignment]

            if signals["ai_summary"]:
                lead.call_summary = signals["ai_summary"]  # type: ignore[assignment]

        campaign = db.query(Campaign).filter(Campaign.campaign_id == call.campaign_id).first()
        if campaign is not None:
            _recalc_campaign_stats(campaign, db)

        db.commit()
        db.refresh(call)
        logger.info(
            f"Call completed: conversation_id={conversation_id} "
            f"outcome={signals['call_outcome']} score={signals['interest_score']}"
        )
        return call

    # ── conversation.failed ───────────────────────────────────────────────────
    if event_type == "conversation.failed":
        error_msg: str = payload.get("error") or payload.get("reason") or "Call failed"
        status: str = str(payload.get("status", "failed"))

        el_status_map = {
            "no_answer": "no_answer",
            "busy": "busy",
            "failed": "failed",
        }
        call.call_status = el_status_map.get(status, "failed")          # type: ignore[assignment]
        call.call_outcome = "no_answer" if status == "no_answer" else "unknown"  # type: ignore[assignment]
        call.error_message = error_msg                                   # type: ignore[assignment]
        call.ended_at = now                                              # type: ignore[assignment]
        call.webhook_payload = payload                                   # type: ignore[assignment]
        call.updated_at = now                                            # type: ignore[assignment]

        lead = db.query(Lead).filter(Lead.lead_id == call.lead_id).first()
        if lead is not None and status == "no_answer":
            lead.call_status = "unreachable"  # type: ignore[assignment]
            lead.updated_at = now              # type: ignore[assignment]

        db.commit()
        logger.info(f"Call failed: conversation_id={conversation_id} status={status}")
        return call

    logger.warning(f"Unhandled webhook event type: {event_type}")
    return None


def fetch_and_store_transcript(call: Call, db: Session) -> Call:
    """
    Manually poll ElevenLabs for a call transcript.
    Fallback if webhook was missed.
    """
    from app.services.elevenlabs_service import get_call_transcript

    # FIX: conversation_id is Column[str] — compare to None explicitly
    if call.conversation_id is None:
        raise ValueError(f"Call {call.call_id} has no conversation_id — cannot fetch transcript")

    data = get_call_transcript(str(call.conversation_id))

    transcript_text: str = data.get("transcript") or ""
    duration_secs = (
        data.get("metadata", {}).get("call_duration_secs")
        or data.get("duration_secs")
    )
    recording_url = (
        data.get("metadata", {}).get("recording_url")
        or data.get("recording_url")
    )
    status: str = str(data.get("status", ""))

    if transcript_text:
        signals = parse_transcript_signals(transcript_text)
        call.transcript = transcript_text                            # type: ignore[assignment]
        call.interest_score = signals["interest_score"]             # type: ignore[assignment]
        call.test_drive_requested = signals["test_drive_requested"] # type: ignore[assignment]
        call.pricing_asked = signals["pricing_asked"]               # type: ignore[assignment]
        call.variant_asked = signals["variant_asked"]               # type: ignore[assignment]
        call.exchange_enquired = signals["exchange_enquired"]       # type: ignore[assignment]
        call.emi_enquired = signals["emi_enquired"]                 # type: ignore[assignment]
        call.ai_summary = signals["ai_summary"]                     # type: ignore[assignment]
        call.call_outcome = signals["call_outcome"]                 # type: ignore[assignment]

    if duration_secs is not None:
        call.call_duration_seconds = int(duration_secs)  # type: ignore[assignment]
    if recording_url is not None:
        call.call_recording_url = recording_url           # type: ignore[assignment]
    if status in ("completed", "failed"):
        call.call_status = "completed" if status == "completed" else "failed"  # type: ignore[assignment]

    call.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()
    db.refresh(call)
    return call


def parse_transcript_signals(transcript: str) -> Dict[str, Any]:
    """
    Parse buying signals from call transcript text.
    Uses keyword matching to score interest 0-10 and classify outcome.
    """
    if not transcript:
        return {
            "interest_score": 0,
            "test_drive_requested": False,
            "pricing_asked": False,
            "variant_asked": False,
            "exchange_enquired": False,
            "emi_enquired": False,
            "competing_model_mentioned": None,
            "ai_summary": None,
            "call_outcome": "unknown",
        }

    text = transcript.lower()

    test_drive_patterns = [
        "test drive", "test car", "try the car", "visit showroom",
        "come to showroom", "want to see", "book a drive", "schedule a visit",
        "test krna", "showroom aana", "dekhna chahta",
    ]
    pricing_patterns = [
        "price", "cost", "how much", "kitna", "rate", "amount",
        "on road price", "ex showroom", "total cost", "discount",
    ]
    emi_patterns = [
        "emi", "loan", "finance", "monthly", "installment",
        "interest rate", "bank loan", "kistey", "maheena",
    ]
    exchange_patterns = [
        "exchange", "trade", "old car", "purani gaadi", "swap",
        "trade-in", "exchange value",
    ]
    variant_patterns = [
        "variant", "version", "zxi", "vxi", "lxi",
        "top model", "base model", "automatic", "manual",
    ]
    not_interested_patterns = [
        "not interested", "no thanks", "don't call", "do not call",
        "nahi chahiye", "nahin chahiye", "nahi lena",
        "remove my number", "stop calling",
    ]
    callback_patterns = [
        "call back", "call later", "baad mein", "callback",
        "discuss with family", "let me check", "will think",
    ]
    competing_brands = [
        "hyundai", "creta", "venue", "nexon", "tata", "punch",
        "kia", "seltos", "sonet", "mahindra", "xuv", "scorpio",
    ]

    test_drive = any(p in text for p in test_drive_patterns)
    pricing = any(p in text for p in pricing_patterns)
    emi = any(p in text for p in emi_patterns)
    exchange = any(p in text for p in exchange_patterns)
    variant = any(p in text for p in variant_patterns)
    not_interested = any(p in text for p in not_interested_patterns)
    callback = any(p in text for p in callback_patterns)

    competing: Optional[str] = None
    for brand in competing_brands:
        if brand in text:
            competing = brand.capitalize()
            break

    score = 0
    if test_drive:   score += 4
    if pricing:      score += 2
    if emi:          score += 2
    if exchange:     score += 2
    if variant:      score += 1
    if competing:    score -= 1
    if not_interested:
        score = max(0, score - 6)
    if callback:
        score = max(score, 3)
    score = min(10, max(0, score))

    if not_interested:
        outcome = "not_interested"
    elif test_drive or score >= 6:
        outcome = "interested"
    elif callback:
        outcome = "callback_requested"
    elif score == 0:
        outcome = "unknown"
    else:
        outcome = "interested"

    summary_parts = []
    if test_drive:      summary_parts.append("Customer requested a test drive.")
    if pricing:         summary_parts.append("Customer asked about pricing.")
    if emi:             summary_parts.append("Customer enquired about EMI / finance options.")
    if exchange:        summary_parts.append("Customer interested in exchange / trade-in.")
    if variant:         summary_parts.append("Customer asked about specific variants.")
    if competing:       summary_parts.append(f"Customer mentioned {competing} as a comparison.")
    if callback:        summary_parts.append("Customer asked for a callback.")
    if not_interested:  summary_parts.append("Customer was not interested.")

    ai_summary = (
        " ".join(summary_parts)
        if summary_parts
        else "Call completed. No strong signals detected."
    )

    return {
        "interest_score": score,
        "test_drive_requested": test_drive,
        "pricing_asked": pricing,
        "variant_asked": variant,
        "exchange_enquired": exchange,
        "emi_enquired": emi,
        "competing_model_mentioned": competing,
        "ai_summary": ai_summary,
        "call_outcome": outcome,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TASK 6.3 — CALL ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

def get_campaign_call_stats(campaign: Campaign, db: Session) -> CampaignCallStats:
    """Aggregate call statistics for a campaign dashboard."""

    calls = db.query(Call).filter(Call.campaign_id == campaign.campaign_id).all()
    leads = db.query(Lead).filter(
        Lead.campaign_id == campaign.campaign_id,
        Lead.deleted_at.is_(None),
        Lead.is_duplicate == False,   # noqa: E712
    ).all()

    total_leads = len(leads)

    # FIX: lead.call_attempts is Column[int] — cast to int before comparing
    leads_called = sum(1 for l in leads if int(l.call_attempts or 0) > 0)  # type: ignore[arg-type]
    leads_pending = sum(1 for l in leads if str(l.call_status) == "new")
    # FIX: lead.do_not_call is Column[bool] — use bool() cast
    leads_dnc = sum(1 for l in leads if bool(l.do_not_call))

    # Call status breakdown — str() cast on Column[str]
    calls_completed   = sum(1 for c in calls if str(c.call_status) == "completed")
    calls_failed      = sum(1 for c in calls if str(c.call_status) == "failed")
    calls_no_answer   = sum(1 for c in calls if str(c.call_status) == "no_answer")
    calls_busy        = sum(1 for c in calls if str(c.call_status) == "busy")
    calls_in_progress = sum(1 for c in calls if str(c.call_status) == "in_progress")

    # Outcome breakdown
    outcome_interested     = sum(1 for c in calls if str(c.call_outcome or "") == "interested")
    outcome_not_interested = sum(1 for c in calls if str(c.call_outcome or "") == "not_interested")
    outcome_callback       = sum(1 for c in calls if str(c.call_outcome or "") == "callback_requested")
    outcome_voicemail      = sum(1 for c in calls if str(c.call_outcome or "") == "voicemail")
    outcome_wrong          = sum(1 for c in calls if str(c.call_outcome or "") == "wrong_number")

    # Buying signals — FIX: bool() cast on Column[bool]
    test_drive_count = sum(1 for c in calls if bool(c.test_drive_requested))
    pricing_count    = sum(1 for c in calls if bool(c.pricing_asked))
    exchange_count   = sum(1 for c in calls if bool(c.exchange_enquired))
    emi_count        = sum(1 for c in calls if bool(c.emi_enquired))

    # Rates
    connection_rate = (
        round(calls_completed / leads_called * 100, 1)
        if leads_called > 0 else 0.0
    )
    interest_rate = (
        round(outcome_interested / calls_completed * 100, 1)
        if calls_completed > 0 else 0.0
    )

    # FIX: call_duration_seconds is Column[int] — cast to int before summing
    durations = [int(c.call_duration_seconds) for c in calls if c.call_duration_seconds is not None]  # type: ignore[arg-type]
    avg_duration: Optional[float] = round(sum(durations) / len(durations), 1) if durations else None
    total_talk_time: int = sum(durations) if durations else 0

    return CampaignCallStats(
        # FIX: Column[UUID] → cast to UUID via str then back won't work cleanly;
        # Pydantic from_attributes handles this, but for direct init we cast to str
        campaign_id=campaign.campaign_id,           # type: ignore[arg-type]
        campaign_name=str(campaign.campaign_name),
        promotion_type=str(campaign.promotion_type),
        total_leads=total_leads,
        leads_called=leads_called,
        leads_pending=leads_pending,
        leads_do_not_call=leads_dnc,
        calls_completed=calls_completed,
        calls_failed=calls_failed,
        calls_no_answer=calls_no_answer,
        calls_busy=calls_busy,
        calls_in_progress=calls_in_progress,
        outcome_interested=outcome_interested,
        outcome_not_interested=outcome_not_interested,
        outcome_callback_requested=outcome_callback,
        outcome_voicemail=outcome_voicemail,
        outcome_wrong_number=outcome_wrong,
        test_drive_requests=test_drive_count,
        pricing_enquiries=pricing_count,
        exchange_enquiries=exchange_count,
        emi_enquiries=emi_count,
        connection_rate=connection_rate,
        interest_rate=interest_rate,
        avg_call_duration_seconds=avg_duration,
        total_talk_time_seconds=total_talk_time,
    )


def get_hot_leads(
    campaign_id: Any,
    db: Session,
    min_score: int = 6,
    limit: int = 50,
) -> List[HotLeadSummary]:
    """Hot leads — high interest score or test drive requested."""

    rows = (
        db.query(Call, Lead)
        .join(Lead, Call.lead_id == Lead.lead_id)
        .filter(
            Call.campaign_id == campaign_id,
            Call.call_status == "completed",
            # FIX: SQLAlchemy OR uses | operator — this is a SQL expression, not Python bool
            (Call.interest_score >= min_score) | (Call.test_drive_requested == True)  # noqa: E712
        )
        .order_by(Call.interest_score.desc().nullslast(), Call.ended_at.desc())
        .limit(limit)
        .all()
    )

    return [
        HotLeadSummary(
            lead_id=lead.lead_id,           # type: ignore[arg-type]
            call_id=call.call_id,           # type: ignore[arg-type]
            name=str(lead.name),
            phone=str(lead.phone),
            email=str(lead.email) if lead.email is not None else None,
            car_interest=str(lead.car_interest) if lead.car_interest is not None else None,
            call_outcome=str(call.call_outcome) if call.call_outcome is not None else "unknown",
            interest_score=int(str(call.interest_score)) if call.interest_score is not None else None,
            test_drive_requested=bool(call.test_drive_requested),
            ai_summary=str(call.ai_summary) if call.ai_summary is not None else None,
            called_at=call.initiated_at,    # type: ignore[arg-type]
        )
        for call, lead in rows
    ]


def get_call_logs(
    campaign_id: Any,
    db: Session,
    call_status: Optional[str] = None,
    call_outcome: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[CallLogEntry]:
    """Paginated call log for a campaign."""

    query = (
        db.query(Call, Lead)
        .join(Lead, Call.lead_id == Lead.lead_id)
        .filter(Call.campaign_id == campaign_id)
    )
    if call_status:
        query = query.filter(Call.call_status == call_status)
    if call_outcome:
        query = query.filter(Call.call_outcome == call_outcome)

    rows = query.order_by(Call.created_at.desc()).offset(skip).limit(limit).all()

    return [
        CallLogEntry(
            call_id=call.call_id,           # type: ignore[arg-type]
            lead_id=lead.lead_id,           # type: ignore[arg-type]
            lead_name=str(lead.name),
            phone_number=str(call.phone_number),
            call_status=str(call.call_status),
            call_outcome=str(call.call_outcome) if call.call_outcome is not None else None,
            call_duration_seconds=int(str(call.call_duration_seconds)) if call.call_duration_seconds is not None else None,
            interest_score=int(str(call.interest_score)) if call.interest_score is not None else None,
            test_drive_requested=bool(call.test_drive_requested) if call.test_drive_requested is not None else None,
            ai_summary=str(call.ai_summary) if call.ai_summary is not None else None,
            initiated_at=call.initiated_at,     # type: ignore[arg-type]
            ended_at=call.ended_at,             # type: ignore[arg-type]
            attempt_number=int(str(call.attempt_number or 1)),
        )
        for call, lead in rows
    ]


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _recalc_campaign_stats(campaign: Campaign, db: Session) -> None:
    """Recompute denormalised lead counters on campaign."""
    base = db.query(Lead).filter(
        Lead.campaign_id == campaign.campaign_id,
        Lead.deleted_at.is_(None),
        Lead.is_duplicate == False,   # noqa: E712
    )
    campaign.total_leads = base.count()                                    # type: ignore[assignment]
    campaign.leads_called = base.filter(Lead.call_attempts > 0).count()   # type: ignore[assignment]
    campaign.leads_interested = base.filter(                               # type: ignore[assignment]
        Lead.interest_level.in_(["hot", "warm"])
    ).count()
    campaign.leads_converted = base.filter(                                # type: ignore[assignment]
        Lead.call_status == "converted"
    ).count()
    campaign.updated_at = datetime.utcnow()                                # type: ignore[assignment]