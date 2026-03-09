"""
Agent Configuration Routes — Day 5
=====================================

Day 5 Task Breakdown:
  Task 5.1 → POST /agents/{campaign_id}/configure  — Create/update ElevenLabs agent
  Task 5.1 → GET  /agents/{campaign_id}            — Get agent config + ElevenLabs status
  Task 5.2 → POST /agents/{campaign_id}/sync-kb    — Push KB to ElevenLabs
  Task 5.2 → GET  /agents/{campaign_id}/kb-status  — Check ElevenLabs KB processing status
             DELETE /agents/{campaign_id}           — Remove agent config + ElevenLabs agent
             GET  /agents/voices                    — List available voices
             GET  /agents/elevenlabs-status         — Test API connection

Full real-world flow:
  1. Campaign is created (Day 4) with status='draft'
  2. Documents uploaded + KB compiled (Day 3)
  3. POST /agents/{campaign_id}/configure
       → Generates system prompt from campaign data
       → Creates ElevenLabs agent via API
       → Stores elevenlabs_agent_id
       → Agent status = 'configured'
  4. POST /agents/{campaign_id}/sync-kb
       → Pushes compiled KB text to ElevenLabs
       → Links KB doc to agent
       → Agent status = 'ready'
  5. Campaign activated (PATCH /campaigns/{id} with status='active')
  6. Day 6: Call Engine picks leads and calls POST /calls/initiate
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.agent_config import AgentConfig
from app.models.campaign import Campaign
from app.models.knowledge_base_model import KnowledgeBase
from app.models.user import User
from app.schemas.agent_schema import (
    AgentConfigCreate, AgentConfigUpdate, AgentConfigResponse,
    KBSyncRequest, ElevenLabsStatusResponse, VoiceOption,
)
from app.services.elevenlabs_service import (
    create_elevenlabs_agent,
    update_elevenlabs_agent,
    get_elevenlabs_agent,
    delete_elevenlabs_agent,
    create_kb_document,
    update_kb_document,
    get_kb_document,
    link_kb_to_agent,
    build_suzuki_system_prompt,
    build_first_message,
    test_elevenlabs_connection,
    VOICE_OPTIONS,
    ElevenLabsAPIError,
)

router = APIRouter(prefix="/agents", tags=["Agent Configuration"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _require_dealership(user: User) -> None:
    if user.dealership_id is None:
        raise HTTPException(
            status_code=400,
            detail="You must create a dealership first (POST /dealership/create)"
        )


def _get_campaign_or_404(campaign_id: str, dealership_id, db: Session) -> Campaign:
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id,
        Campaign.dealership_id == dealership_id,
        Campaign.deleted_at.is_(None)
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return campaign


def _get_agent_or_404(campaign_id: str, db: Session) -> AgentConfig:
    agent = db.query(AgentConfig).filter(
        AgentConfig.campaign_id == campaign_id
    ).first()
    if not agent:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No agent configured for campaign {campaign_id}. "
                f"Run POST /agents/{campaign_id}/configure first."
            )
        )
    return agent


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/elevenlabs-status", response_model=ElevenLabsStatusResponse)
def check_elevenlabs_status(
    current_user: User = Depends(get_current_user),
):
    """
    Test ElevenLabs API connectivity and API key validity.

    Real-world use: Before configuring agents, verify:
      1. ELEVENLABS_API_KEY is set in environment
      2. Key is valid and has enough character quota
      3. API is reachable

    Returns subscription tier and character usage.
    """
    import os
    api_key_set = bool(os.getenv("ELEVENLABS_API_KEY", ""))

    status = test_elevenlabs_connection()

    voices = [
        VoiceOption(
            voice_id=vid,
            name=name,
            description=_voice_description(name)
        )
        for name, vid in VOICE_OPTIONS.items()
    ]

    return ElevenLabsStatusResponse(
        connected=status.get("connected", False),
        api_key_set=api_key_set,
        subscription=status.get("subscription"),
        character_count=status.get("character_count"),
        character_limit=status.get("character_limit"),
        error=status.get("error"),
        available_voices=voices,
    )


def _voice_description(name: str) -> str:
    descriptions = {
        "Jessica": "Clear female voice, neutral accent — recommended for sales calls",
        "Adam":    "Professional male voice, neutral accent",
        "Aria":    "Warm female voice, engaging tone",
        "Roger":   "Deep male voice, authoritative",
        "Sarah":   "Soft female voice, empathetic",
    }
    return descriptions.get(name, "ElevenLabs voice")


@router.get("/voices")
def list_voices(current_user: User = Depends(get_current_user)):
    """
    List available ElevenLabs voices for agent configuration.

    Real-world: Sales manager picks the voice that sounds most natural
    for their customer demographic and language preference.
    """
    return {
        "voices": [
            {
                "voice_id": vid,
                "name": name,
                "description": _voice_description(name),
                "recommended_for": _voice_recommendation(name),
            }
            for name, vid in VOICE_OPTIONS.items()
        ],
        "tip": (
            "For Indian customers calling in English, 'Jessica' or 'Aria' work best. "
            "For Hindi campaigns, 'Adam' or 'Roger' are preferred by male customers."
        )
    }


def _voice_recommendation(name: str) -> str:
    recs = {
        "Jessica": "English outbound, urban customers",
        "Adam":    "English outbound, professional segment",
        "Aria":    "English or Hindi-English mix calls",
        "Roger":   "Corporate / fleet sales calls",
        "Sarah":   "Follow-up calls, existing customers",
    }
    return recs.get(name, "General use")


# ══════════════════════════════════════════════════════════════════════════════
# TASK 5.1 — AGENT CREATION & CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{campaign_id}/configure", response_model=AgentConfigResponse, status_code=201)
def configure_agent(
    campaign_id: str,
    body: AgentConfigCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create or reconfigure the ElevenLabs AI agent for a campaign.

    **Task 5.1 — Agent Configuration**

    This endpoint:
    1. Fetches campaign + dealership details for context
    2. Auto-generates a Suzuki-specific system prompt (if not provided)
    3. Calls ElevenLabs API to create the agent
    4. Stores the returned `elevenlabs_agent_id` for future calls
    5. Sets agent status to 'configured'

    After this, run POST /agents/{campaign_id}/sync-kb to link the knowledge base.

    **If agent already exists**: updates the existing ElevenLabs agent + our config.

    Real-world: Sales manager runs this once after setting up the campaign.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    # Load dealership for prompt context
    try:
        from app.models.dealership import Dealership
        dealership = db.query(Dealership).filter(
            Dealership.dealership_id == current_user.dealership_id
        ).first()
        dealership_name = str(dealership.name) if dealership else "Suzuki Dealership"
    except Exception:
        dealership_name = "Suzuki Dealership"

    # Load car model if linked
    car_model_name: Optional[str] = None
    if campaign.car_model_id is not None:
        try:
            from app.models.car_model import CarModel
            car = db.query(CarModel).filter(
                CarModel.car_model_id == campaign.car_model_id
            ).first()
            if car:
                car_model_name = str(car.model_name)
        except Exception:
            pass

    # ── Build prompts ──────────────────────────────────────────────────────────
    language = body.language or "en"

    system_prompt = body.system_prompt or build_suzuki_system_prompt(
        dealership_name=dealership_name,
        campaign_name=str(campaign.campaign_name),
        campaign_description=str(campaign.description) if campaign.description is not None else None,
        car_model_name=car_model_name,
        promotion_type=str(campaign.promotion_type) if campaign.promotion_type is not None else None,
        language=language,
    )

    first_message = body.first_message or build_first_message(
        agent_name="Priya",
        dealership_name=dealership_name,
        lead_name=None,                 # generic — personalized per call via dynamic vars
        campaign_name=str(campaign.campaign_name),
        language=language,
    )

    # ── Check if agent already exists for this campaign ────────────────────────
    existing_agent = db.query(AgentConfig).filter(
        AgentConfig.campaign_id == campaign_id
    ).first()

    now = datetime.utcnow()

    try:
        if existing_agent is not None and existing_agent.elevenlabs_agent_id is not None:
            # ── UPDATE existing ElevenLabs agent ──────────────────────────────
            update_elevenlabs_agent(
                elevenlabs_agent_id=str(existing_agent.elevenlabs_agent_id),
                system_prompt=system_prompt,
                first_message=first_message,
                voice_id=body.voice_id,
                language=language,
                max_duration_secs=body.max_call_duration_secs,
            )

            # Update our DB record
            existing_agent.voice_id = body.voice_id or existing_agent.voice_id          # type: ignore[assignment]
            existing_agent.voice_name = body.voice_name or existing_agent.voice_name    # type: ignore[assignment]
            existing_agent.system_prompt = system_prompt                                  # type: ignore[assignment]
            existing_agent.first_message = first_message                                  # type: ignore[assignment]
            existing_agent.language = language                                            # type: ignore[assignment]
            existing_agent.max_call_duration_secs = body.max_call_duration_secs or 300  # type: ignore[assignment]
            existing_agent.stability = body.stability or 0.5                             # type: ignore[assignment]
            existing_agent.similarity_boost = body.similarity_boost or 0.75             # type: ignore[assignment]
            existing_agent.status = "configured"                                          # type: ignore[assignment]
            existing_agent.error_message = None                                           # type: ignore[assignment]
            existing_agent.updated_at = now                                               # type: ignore[assignment]

            if body.knowledge_base_id:
                existing_agent.knowledge_base_id = body.knowledge_base_id  # type: ignore[assignment]

            db.commit()
            db.refresh(existing_agent)
            return existing_agent

        else:
            # ── CREATE new ElevenLabs agent ────────────────────────────────────
            agent_name = f"{dealership_name} — {campaign.campaign_name}"[:100]

            el_result = create_elevenlabs_agent(
                agent_name=agent_name,
                system_prompt=system_prompt,
                first_message=first_message,
                voice_id=body.voice_id or "cgSgspJ2msm6clMCkdW9",
                language=language,
                max_duration_secs=body.max_call_duration_secs or 300,
                stability=body.stability or 0.5,
                similarity_boost=body.similarity_boost or 0.75,
            )

            elevenlabs_agent_id = el_result.get("agent_id")
            if not elevenlabs_agent_id:
                raise HTTPException(
                    status_code=502,
                    detail="ElevenLabs returned success but no agent_id. Check ElevenLabs dashboard."
                )

            # ── Save to DB ─────────────────────────────────────────────────────
            if existing_agent:
                # Had config record but no EL agent ID — update in place
                existing_agent.elevenlabs_agent_id = elevenlabs_agent_id   # type: ignore[assignment]
                existing_agent.voice_id = body.voice_id or "cgSgspJ2msm6clMCkdW9"  # type: ignore[assignment]
                existing_agent.voice_name = body.voice_name or "Jessica"    # type: ignore[assignment]
                existing_agent.system_prompt = system_prompt                 # type: ignore[assignment]
                existing_agent.first_message = first_message                 # type: ignore[assignment]
                existing_agent.language = language                           # type: ignore[assignment]
                existing_agent.max_call_duration_secs = body.max_call_duration_secs or 300  # type: ignore[assignment]
                existing_agent.stability = body.stability or 0.5            # type: ignore[assignment]
                existing_agent.similarity_boost = body.similarity_boost or 0.75  # type: ignore[assignment]
                existing_agent.status = "configured"                         # type: ignore[assignment]
                existing_agent.error_message = None                          # type: ignore[assignment]
                existing_agent.knowledge_base_id = body.knowledge_base_id   # type: ignore[assignment]
                existing_agent.dealership_id = current_user.dealership_id   # type: ignore[assignment]
                existing_agent.updated_at = now                              # type: ignore[assignment]
                db.commit()
                db.refresh(existing_agent)
                return existing_agent
            else:
                agent_config = AgentConfig(
                    agent_id=uuid.uuid4(),
                    campaign_id=uuid.UUID(campaign_id),
                    dealership_id=current_user.dealership_id,
                    created_by=current_user.user_id,
                    elevenlabs_agent_id=elevenlabs_agent_id,
                    voice_id=body.voice_id or "cgSgspJ2msm6clMCkdW9",
                    voice_name=body.voice_name or "Jessica",
                    system_prompt=system_prompt,
                    first_message=first_message,
                    language=language,
                    max_call_duration_secs=body.max_call_duration_secs or 300,
                    stability=body.stability or 0.5,
                    similarity_boost=body.similarity_boost or 0.75,
                    knowledge_base_id=body.knowledge_base_id,
                    status="configured",
                    created_at=now,
                    updated_at=now,
                )
                db.add(agent_config)
                db.commit()
                db.refresh(agent_config)
                return agent_config

    except ElevenLabsAPIError as e:
        # Store the error in DB if we have a config record
        if existing_agent:
            existing_agent.status = "error"          # type: ignore[assignment]
            existing_agent.error_message = e.message  # type: ignore[assignment]
            existing_agent.updated_at = now           # type: ignore[assignment]
            db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "error": "elevenlabs_api_error",
                "message": e.message,
                "status_code": e.status_code,
                "hint": (
                    "Check your ELEVENLABS_API_KEY and account status at "
                    "https://elevenlabs.io/app/settings/api-keys"
                )
            }
        )


@router.get("/{campaign_id}", response_model=AgentConfigResponse)
def get_agent_config(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get agent configuration for a campaign.

    Returns full config including ElevenLabs agent ID, KB sync status,
    and current agent status.
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    return _get_agent_or_404(campaign_id, db)


@router.patch("/{campaign_id}", response_model=AgentConfigResponse)
def update_agent_config(
    campaign_id: str,
    body: AgentConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update agent voice, prompt, or settings.

    Also pushes changes to the live ElevenLabs agent if one exists.
    Use this to:
    - Change voice mid-campaign
    - Tweak the system prompt
    - Update call duration limits
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    agent = _get_agent_or_404(campaign_id, db)

    now = datetime.utcnow()
    update_data = body.dict(exclude_unset=True)

    for field, value in update_data.items():
        setattr(agent, field, value)
    agent.updated_at = now  # type: ignore[assignment]

    # Push changes to ElevenLabs if agent exists there
    if agent.elevenlabs_agent_id is not None:
        try:
            update_elevenlabs_agent(
                elevenlabs_agent_id=str(agent.elevenlabs_agent_id),
                system_prompt=body.system_prompt,
                first_message=body.first_message,
                voice_id=body.voice_id,
                language=body.language,
                max_duration_secs=body.max_call_duration_secs,
            )
        except ElevenLabsAPIError as e:
            agent.error_message = f"ElevenLabs sync failed: {e.message}"  # type: ignore[assignment]
            agent.status = "error"  # type: ignore[assignment]
            db.commit()
            raise HTTPException(
                status_code=502,
                detail={"error": "elevenlabs_sync_failed", "message": e.message}
            )

    db.commit()
    db.refresh(agent)
    return agent


@router.delete("/{campaign_id}")
def delete_agent_config(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete agent configuration and remove ElevenLabs agent.

    Real-world: Used when a campaign is being reset or deleted.
    The ElevenLabs agent is also deleted to avoid orphaned agents.
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    agent = _get_agent_or_404(campaign_id, db)

    # Delete from ElevenLabs first
    if agent.elevenlabs_agent_id is not None:
        try:
            delete_elevenlabs_agent(str(agent.elevenlabs_agent_id))
        except Exception as e:
            # Non-fatal — log and continue with local deletion
            import logging
            logging.getLogger(__name__).warning(
                f"Could not delete ElevenLabs agent {agent.elevenlabs_agent_id}: {e}"
            )

    db.delete(agent)
    db.commit()
    return {"message": f"Agent configuration deleted for campaign {campaign_id}"}


# ══════════════════════════════════════════════════════════════════════════════
# TASK 5.2 — KNOWLEDGE BASE SYNC
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{campaign_id}/sync-kb")
def sync_knowledge_base(
    campaign_id: str,
    body: KBSyncRequest = KBSyncRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Push compiled knowledge base to ElevenLabs and link it to the agent.

    **Task 5.2 — Knowledge Base Sync**

    This endpoint:
    1. Loads the compiled KB text from our database
    2. Uploads it to ElevenLabs as a knowledge base document
    3. Links the KB document to the ElevenLabs agent
    4. Stores the elevenlabs_kb_id for reference
    5. Updates agent status to 'ready'

    Prerequisites:
    - Agent must be configured (POST /agents/{campaign_id}/configure done)
    - Knowledge base must be compiled (POST /kb/{id}/compile done)

    ElevenLabs processes the KB asynchronously. Use GET /agents/{campaign_id}/kb-status
    to check when processing is complete (status: 'in_progress' → 'processed').

    After status = 'ready', the agent can answer questions from the brochures.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    agent = _get_agent_or_404(campaign_id, db)

    if agent.elevenlabs_agent_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Agent not configured with ElevenLabs yet. "
                f"Run POST /agents/{campaign_id}/configure first."
            )
        )

    # Resolve which KB to use
    kb_id = body.knowledge_base_id or agent.knowledge_base_id or campaign.knowledge_base_id
    if kb_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No knowledge base linked to this agent or campaign. "
                "Either: (a) pass knowledge_base_id in request body, "
                "or (b) link a KB to the campaign via PATCH /campaigns/{id}, "
                "or (c) set knowledge_base_id when configuring the agent."
            )
        )

    # Load the KB
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.kb_id == kb_id,
        KnowledgeBase.dealership_id == current_user.dealership_id,
    ).first()

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if kb.status != "ready":   # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=422,
            detail=(
                f"Knowledge base status is '{kb.status}' — must be 'ready' before syncing. "
                f"Run POST /kb/{kb_id}/compile first."
            )
        )

    compiled_content = kb.compiled_content  # type: ignore[union-attr]
    if compiled_content is None:
        raise HTTPException(
            status_code=422,
            detail="Knowledge base has no compiled content. Run POST /kb/{kb_id}/compile."
        )

    now = datetime.utcnow()
    kb_doc_name = f"suzuki-kb-{str(campaign.campaign_name)[:50].lower().replace(' ', '-')}"

    try:
        # ── Step 1: Upload or update KB document on ElevenLabs ────────────────
        if agent.elevenlabs_kb_id is not None:
            # KB doc already exists — update with fresh content
            kb_result = update_kb_document(
                elevenlabs_kb_doc_id=str(agent.elevenlabs_kb_id),
                name=kb_doc_name,
                text_content=str(compiled_content),
            )
            elevenlabs_kb_doc_id = str(agent.elevenlabs_kb_id)
        else:
            # First sync — create new KB document
            kb_result = create_kb_document(
                name=kb_doc_name,
                text_content=str(compiled_content),
            )
            elevenlabs_kb_doc_id = kb_result.get("id", "")

            if not elevenlabs_kb_doc_id:
                raise HTTPException(
                    status_code=502,
                    detail="ElevenLabs returned success but no document ID. Try again."
                )

        # ── Step 2: Link KB document to agent ─────────────────────────────────
        link_kb_to_agent(
            elevenlabs_agent_id=str(agent.elevenlabs_agent_id),
            elevenlabs_kb_doc_id=elevenlabs_kb_doc_id,
            kb_name=kb_doc_name,
        )

        # ── Step 3: Update agent_config in DB ─────────────────────────────────
        agent.elevenlabs_kb_id = elevenlabs_kb_doc_id    # type: ignore[assignment]
        agent.knowledge_base_id = kb_id                  # type: ignore[assignment]
        agent.kb_synced_at = now                         # type: ignore[assignment]
        agent.kb_sync_status = "synced"                  # type: ignore[assignment]
        agent.kb_sync_error = None                       # type: ignore[assignment]
        agent.status = "ready"                           # type: ignore[assignment]
        agent.error_message = None                       # type: ignore[assignment]
        agent.updated_at = now                           # type: ignore[assignment]
        db.commit()
        db.refresh(agent)

        return {
            "message": "Knowledge base synced to ElevenLabs successfully.",
            "agent_id": str(agent.agent_id),
            "elevenlabs_agent_id": str(agent.elevenlabs_agent_id),
            "elevenlabs_kb_id": elevenlabs_kb_doc_id,
            "kb_name": kb_doc_name,
            "kb_word_count": kb.word_count,
            "agent_status": "ready",
            "next_step": (
                "Your agent is now ready! "
                "Check GET /agents/{campaign_id}/kb-status to confirm ElevenLabs has processed the KB. "
                "Then activate your campaign: PATCH /campaigns/{campaign_id} with status='active'."
            ),
        }

    except ElevenLabsAPIError as e:
        # Mark sync as failed
        agent.kb_sync_status = "failed"        # type: ignore[assignment]
        agent.kb_sync_error = e.message        # type: ignore[assignment]
        agent.status = "configured"            # type: ignore[assignment]  # reset to pre-sync state
        agent.updated_at = now                 # type: ignore[assignment]
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "error": "kb_sync_failed",
                "message": e.message,
                "hint": "Check ELEVENLABS_API_KEY and your ElevenLabs account quota.",
            }
        )


@router.get("/{campaign_id}/kb-status")
def get_kb_processing_status(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Check if ElevenLabs has finished processing the knowledge base.

    ElevenLabs processes KB documents asynchronously after upload.
    Status: "in_progress" → "processed" (usually takes 10-60 seconds).

    The agent can only answer from the KB once status = "processed".
    Poll this endpoint after sync-kb until you see "processed".
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    agent = _get_agent_or_404(campaign_id, db)

    if agent.elevenlabs_kb_id is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "No KB synced yet. "
                f"Run POST /agents/{campaign_id}/sync-kb first."
            )
        )

    try:
        kb_doc = get_kb_document(str(agent.elevenlabs_kb_id))
        el_status = kb_doc.get("status", "unknown")

        # Map ElevenLabs status to readable format
        status_map = {
            "in_progress": "ElevenLabs is processing your knowledge base (usually 10-60 seconds).",
            "processed":   "Knowledge base is processed and ready. Agent can now answer questions.",
            "error":       "ElevenLabs encountered an error processing the KB. Re-sync recommended.",
        }

        return {
            "elevenlabs_kb_id": str(agent.elevenlabs_kb_id),
            "elevenlabs_status": el_status,
            "message": status_map.get(el_status, f"Unknown status: {el_status}"),
            "agent_status": agent.status,
            "kb_synced_at": agent.kb_synced_at.isoformat() if agent.kb_synced_at is not None else None,
            "ready_for_calls": el_status == "processed" and agent.status == "ready",
        }

    except ElevenLabsAPIError as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "elevenlabs_api_error", "message": e.message}
        )


@router.get("/{campaign_id}/preview-prompt")
def preview_agent_prompt(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Preview the system prompt and first message for a campaign's agent.

    Useful for reviewing before pushing to ElevenLabs.
    Call this BEFORE /configure to see what the auto-generated prompt looks like.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    try:
        from app.models.dealership import Dealership
        dealership = db.query(Dealership).filter(
            Dealership.dealership_id == current_user.dealership_id
        ).first()
        dealership_name = str(dealership.name) if dealership else "Suzuki Dealership"
    except Exception:
        dealership_name = "Suzuki Dealership"

    car_model_name: Optional[str] = None
    if campaign.car_model_id is not None:
        try:
            from app.models.car_model import CarModel
            car = db.query(CarModel).filter(
                CarModel.car_model_id == campaign.car_model_id
            ).first()
            if car:
                car_model_name = str(car.model_name)
        except Exception:
            pass

    system_prompt = build_suzuki_system_prompt(
        dealership_name=dealership_name,
        campaign_name=str(campaign.campaign_name),
        campaign_description=str(campaign.description) if campaign.description is not None else None,
        car_model_name=car_model_name,
        promotion_type=str(campaign.promotion_type) if campaign.promotion_type is not None else None,
        language="en",
    )

    first_message_en = build_first_message(
        agent_name="Priya",
        dealership_name=dealership_name,
        lead_name=None,
        campaign_name=str(campaign.campaign_name),
        language="en",
    )
    first_message_hi = build_first_message(
        agent_name="Priya",
        dealership_name=dealership_name,
        lead_name=None,
        campaign_name=str(campaign.campaign_name),
        language="hi",
    )

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.campaign_name,
        "auto_generated_system_prompt": system_prompt,
        "first_message_english": first_message_en,
        "first_message_hindi": first_message_hi,
        "prompt_word_count": len(system_prompt.split()),
        "note": (
            "This is the auto-generated prompt. You can customize it by passing "
            "'system_prompt' and 'first_message' in POST /agents/{campaign_id}/configure."
        )
    }
