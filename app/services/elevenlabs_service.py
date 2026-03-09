"""
ElevenLabs Conversational AI Integration Service
=================================================

Day 5 — ElevenLabs AI Agent Integration

This service handles ALL communication with the ElevenLabs Conversational AI API:

  Task 5.1 — Agent Creation & Configuration
    create_elevenlabs_agent()     → POST /v1/convai/agents/create
    update_elevenlabs_agent()     → PATCH /v1/convai/agents/{agent_id}
    get_elevenlabs_agent()        → GET  /v1/convai/agents/{agent_id}
    delete_elevenlabs_agent()     → DELETE /v1/convai/agents/{agent_id}

  Task 5.2 — Knowledge Base Sync
    create_kb_document()          → POST /v1/convai/knowledge-base/document
    update_kb_document()          → PATCH /v1/convai/knowledge-base/{kb_doc_id}
    get_kb_document()             → GET  /v1/convai/knowledge-base/{kb_doc_id}
    add_kb_to_agent()             → PATCH /v1/convai/agents/{agent_id} (link KB)

  Task 5.3 — Outbound Call (Day 6 will use this)
    initiate_outbound_call()      → POST /v1/convai/twilio/outbound-call
                                     (ElevenLabs + Twilio for outbound)

ElevenLabs Conversational AI Docs:
  https://elevenlabs.io/docs/conversational-ai/api-reference

Environment variables required:
  ELEVENLABS_API_KEY  — from ElevenLabs dashboard → API Keys

Real-world Suzuki dealership prompt strategy:
  The system prompt defines the agent as a Suzuki sales representative.
  The KB document contains compiled brochure/pricing/feature data.
  ElevenLabs RAG automatically retrieves relevant KB snippets per user query.
"""

import os
import logging
from typing import Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

# ── ElevenLabs API Config ─────────────────────────────────────────────────────
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")

# Timeout for ElevenLabs API calls (seconds)
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# ── Default voice IDs (ElevenLabs built-in voices) ───────────────────────────
# These are stable ElevenLabs voice IDs — no need to create custom voices
VOICE_OPTIONS = {
    "Jessica": "cgSgspJ2msm6clMCkdW9",   # Clear female, neutral — recommended default
    "Adam":    "pNInz6obpgDQGcFmaJgB",   # Professional male, neutral
    "Aria":    "9BWtsMINqrJLrRacOk9x",   # Warm female
    "Roger":   "CwhRBWXzGAHq8TQ4Fs17",   # Deep male, authoritative
    "Sarah":   "EXAVITQu4vr4xnSDxMaL",   # Soft female
}

# ── Default Suzuki Sales Prompt ───────────────────────────────────────────────
DEFAULT_SUZUKI_PROMPT = """You are Priya, a friendly and knowledgeable Suzuki automobile sales representative calling on behalf of {dealership_name}. 

Your goal is to:
1. Introduce yourself warmly and mention the specific campaign or promotion
2. Briefly highlight key benefits of the car model being promoted
3. Answer any questions the customer has using ONLY the information provided in your knowledge base
4. Qualify the customer's interest level (budget, timeline, current vehicle)
5. Offer to schedule a test drive or send detailed information via WhatsApp

IMPORTANT RULES:
- Answer questions ONLY from your knowledge base. If you don't know something, say "Let me connect you with our sales team for that detail."
- Never make up prices, features, or specifications not in your knowledge base
- Be conversational and natural — this is a phone call, not a formal presentation
- Keep responses concise — 2-3 sentences maximum per turn
- If the customer is not interested, thank them politely and end the call
- Detect and respond to the customer's language preference (Hindi/English/Regional)
- Always mention the dealership name: {dealership_name}

Campaign focus: {campaign_description}
"""

DEFAULT_FIRST_MESSAGE = (
    "Namaste! Main {agent_name} bol rahi hoon {dealership_name} ki taraf se. "
    "Kya main aapka ek minute le sakti hoon? "
    "Humara ek exciting offer hai jo main aapke saath share karna chahti hoon."
)


# ══════════════════════════════════════════════════════════════════════════════
# HTTP CLIENT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _headers() -> Dict[str, str]:
    """Build auth headers for ElevenLabs API."""
    if not ELEVENLABS_API_KEY:
        raise ValueError(
            "ELEVENLABS_API_KEY environment variable is not set. "
            "Get your key from https://elevenlabs.io/app/settings/api-keys"
        )
    return {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }


def _handle_response(response: httpx.Response, operation: str) -> Dict[str, Any]:
    """Parse ElevenLabs API response and raise descriptive errors."""
    if response.status_code in (200, 201):
        return response.json()

    # Parse ElevenLabs error format
    try:
        err_body = response.json()
        err_detail = err_body.get("detail", {})
        if isinstance(err_detail, dict):
            message = err_detail.get("message", str(err_body))
        else:
            message = str(err_detail) or str(err_body)
    except Exception:
        message = response.text or f"HTTP {response.status_code}"

    logger.error(f"ElevenLabs {operation} failed [{response.status_code}]: {message}")
    raise ElevenLabsAPIError(
        status_code=response.status_code,
        message=f"ElevenLabs {operation} error: {message}",
        operation=operation,
    )


class ElevenLabsAPIError(Exception):
    """Raised when ElevenLabs API returns an error."""
    def __init__(self, status_code: int, message: str, operation: str = ""):
        self.status_code = status_code
        self.message = message
        self.operation = operation
        super().__init__(message)


# ══════════════════════════════════════════════════════════════════════════════
# TASK 5.1 — AGENT CREATION & CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

def create_elevenlabs_agent(
    agent_name: str,
    system_prompt: str,
    first_message: str,
    voice_id: str,
    language: str = "en",
    max_duration_secs: int = 300,
    stability: float = 0.5,
    similarity_boost: float = 0.75,
) -> Dict[str, Any]:
    """
    Create a new ElevenLabs Conversational AI agent.

    POST /v1/convai/agents/create

    ElevenLabs agent config structure:
      - conversation_config.agent.prompt.prompt → system prompt
      - conversation_config.agent.first_message → greeting
      - conversation_config.tts.voice_id         → ElevenLabs voice
      - conversation_config.agent.language       → call language

    Returns the full agent object including agent_id (used for outbound calls).
    """
    payload = {
        "name": agent_name,
        "conversation_config": {
            "agent": {
                "prompt": {
                    "prompt": system_prompt,
                    "llm": "gemini-2.0-flash",       # Fast, cost-effective LLM
                    "temperature": 0.5,
                    "knowledge_base": [],            # KB docs added separately
                },
                "first_message": first_message,
                "language": language,
            },
            "tts": {
                "model_id": "eleven_turbo_v2_5",     # Low latency for real-time calls
                "voice_id": voice_id,
                "stability": stability,
                "similarity_boost": similarity_boost,
                "optimize_streaming_latency": 3,
            },
            "turn": {
                "turn_timeout": 7,        # seconds to wait for customer response
                "silence_end_call_timeout": 20,  # hang up after 20s silence
            },
            "conversation": {
                "max_duration_seconds": max_duration_secs,
                "client_events": [
                    "audio",
                    "interruption",
                    "agent_response",
                    "user_transcript",
                ],
            },
        },
        "platform_settings": {
            "auth": {
                "enable_auth": False,        # outbound calls — no PIN needed
            },
            "call_limits": {
                "agent_concurrency_limit": 5,  # max 5 simultaneous calls
            },
        },
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(
            f"{ELEVENLABS_API_BASE}/convai/agents/create",
            headers=_headers(),
            json=payload,
        )

    result = _handle_response(response, "create_agent")
    logger.info(f"ElevenLabs agent created: {result.get('agent_id')}")
    return result


def update_elevenlabs_agent(
    elevenlabs_agent_id: str,
    system_prompt: Optional[str] = None,
    first_message: Optional[str] = None,
    voice_id: Optional[str] = None,
    language: Optional[str] = None,
    max_duration_secs: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Update an existing ElevenLabs agent.

    PATCH /v1/convai/agents/{agent_id}

    Only sends fields that are provided (partial update).
    Used when dealership wants to change voice, prompt, or settings.
    """
    payload: Dict[str, Any] = {"conversation_config": {"agent": {}, "tts": {}}}

    if system_prompt:
        payload["conversation_config"]["agent"]["prompt"] = {"prompt": system_prompt}
    if first_message:
        payload["conversation_config"]["agent"]["first_message"] = first_message
    if language:
        payload["conversation_config"]["agent"]["language"] = language
    if voice_id:
        payload["conversation_config"]["tts"]["voice_id"] = voice_id
    if max_duration_secs:
        payload["conversation_config"]["conversation"] = {
            "max_duration_seconds": max_duration_secs
        }

    # Clean up empty dicts
    if not payload["conversation_config"]["agent"]:
        del payload["conversation_config"]["agent"]
    if not payload["conversation_config"]["tts"]:
        del payload["conversation_config"]["tts"]

    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.patch(
            f"{ELEVENLABS_API_BASE}/convai/agents/{elevenlabs_agent_id}",
            headers=_headers(),
            json=payload,
        )

    result = _handle_response(response, "update_agent")
    logger.info(f"ElevenLabs agent updated: {elevenlabs_agent_id}")
    return result


def get_elevenlabs_agent(elevenlabs_agent_id: str) -> Dict[str, Any]:
    """
    Get an ElevenLabs agent's current config.

    GET /v1/convai/agents/{agent_id}
    """
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{ELEVENLABS_API_BASE}/convai/agents/{elevenlabs_agent_id}",
            headers=_headers(),
        )
    return _handle_response(response, "get_agent")


def delete_elevenlabs_agent(elevenlabs_agent_id: str) -> bool:
    """
    Delete an ElevenLabs agent.

    DELETE /v1/convai/agents/{agent_id}
    Used when campaign is deleted or agent is being reset.
    """
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.delete(
            f"{ELEVENLABS_API_BASE}/convai/agents/{elevenlabs_agent_id}",
            headers=_headers(),
        )
    if response.status_code in (200, 204):
        logger.info(f"ElevenLabs agent deleted: {elevenlabs_agent_id}")
        return True
    # Non-critical — log and continue
    logger.warning(f"ElevenLabs agent delete returned {response.status_code}: {response.text}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# TASK 5.2 — KNOWLEDGE BASE SYNC
# ══════════════════════════════════════════════════════════════════════════════

def create_kb_document(
    name: str,
    text_content: str,
) -> Dict[str, Any]:
    """
    Upload compiled KB text to ElevenLabs as a knowledge base document.

    POST /v1/convai/knowledge-base/document

    ElevenLabs stores the document and makes it searchable via RAG.
    When a customer asks "What is the price of Brezza ZXi+?", ElevenLabs
    automatically searches this document and injects relevant snippets
    into the agent's context.

    Returns: { "id": "kb_doc_xxxxx", "name": "...", ... }
    The returned "id" is what we store as elevenlabs_kb_id in agent_config.
    """
    # ElevenLabs accepts multipart form upload for KB documents
    # We send text as a .txt file
    files = {
        "file": (f"{name}.txt", text_content.encode("utf-8"), "text/plain"),
    }
    # No Content-Type header — httpx sets it automatically for multipart
    headers = {"xi-api-key": ELEVENLABS_API_KEY}

    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        response = client.post(
            f"{ELEVENLABS_API_BASE}/convai/knowledge-base/document",
            headers=headers,
            files=files,
            data={"name": name},
        )

    result = _handle_response(response, "create_kb_document")
    logger.info(f"ElevenLabs KB document created: {result.get('id')}")
    return result


def update_kb_document(
    elevenlabs_kb_doc_id: str,
    name: str,
    text_content: str,
) -> Dict[str, Any]:
    """
    Update an existing KB document with fresh compiled content.

    PATCH /v1/convai/knowledge-base/{documentation_id}

    Called when the dealership re-compiles the KB (new brochure uploaded,
    pricing updated, etc.). Keeps the same KB doc ID on the ElevenLabs side
    so linked agents automatically get the updated content.
    """
    files = {
        "file": (f"{name}.txt", text_content.encode("utf-8"), "text/plain"),
    }
    headers = {"xi-api-key": ELEVENLABS_API_KEY}

    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
        response = client.patch(
            f"{ELEVENLABS_API_BASE}/convai/knowledge-base/{elevenlabs_kb_doc_id}",
            headers=headers,
            files=files,
            data={"name": name},
        )

    result = _handle_response(response, "update_kb_document")
    logger.info(f"ElevenLabs KB document updated: {elevenlabs_kb_doc_id}")
    return result


def get_kb_document(elevenlabs_kb_doc_id: str) -> Dict[str, Any]:
    """
    Get status of a KB document.

    GET /v1/convai/knowledge-base/{documentation_id}

    ElevenLabs processes KB docs asynchronously.
    Status: "in_progress" → "processed" | "error"
    Poll this until status = "processed" before using agent for calls.
    """
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{ELEVENLABS_API_BASE}/convai/knowledge-base/{elevenlabs_kb_doc_id}",
            headers=_headers(),
        )
    return _handle_response(response, "get_kb_document")


def link_kb_to_agent(
    elevenlabs_agent_id: str,
    elevenlabs_kb_doc_id: str,
    kb_name: str,
) -> Dict[str, Any]:
    """
    Link a KB document to an ElevenLabs agent.

    PATCH /v1/convai/agents/{agent_id}
    — updates knowledge_base list in agent's prompt config

    After this, the agent will use RAG to answer from the KB document
    whenever a customer asks a question it can't answer from the prompt alone.
    """
    payload = {
        "conversation_config": {
            "agent": {
                "prompt": {
                    "knowledge_base": [
                        {
                            "type": "file",
                            "id": elevenlabs_kb_doc_id,
                            "name": kb_name,
                        }
                    ]
                }
            }
        }
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.patch(
            f"{ELEVENLABS_API_BASE}/convai/agents/{elevenlabs_agent_id}",
            headers=_headers(),
            json=payload,
        )

    result = _handle_response(response, "link_kb_to_agent")
    logger.info(
        f"KB doc {elevenlabs_kb_doc_id} linked to agent {elevenlabs_agent_id}"
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# TASK 5.3 — OUTBOUND CALL (Day 6 will complete this module)
# ══════════════════════════════════════════════════════════════════════════════

def initiate_outbound_call(
    elevenlabs_agent_id: str,
    phone_number: str,
    agent_phone_number_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Initiate an outbound call via ElevenLabs + Twilio.

    POST /v1/convai/twilio/outbound-call

    Prerequisites:
      1. ElevenLabs agent must be configured with elevenlabs_agent_id
      2. A Twilio phone number must be connected in ElevenLabs dashboard
         (Settings → Telephony → Add Twilio number)
      3. The agent_phone_number_id is the ElevenLabs ID for the connected Twilio number

    phone_number must be in E.164 format: +91XXXXXXXXXX

    metadata: Optional dict passed through to the call — useful for
              tracking which lead/campaign triggered the call.
              Available in call transcripts and webhook events.

    Returns: { "call_id": "...", "status": "initiated" }
    The call_id is stored in the calls table for tracking (Day 6).
    """
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY not set")

    payload: Dict[str, Any] = {
        "agent_id": elevenlabs_agent_id,
        "agent_phone_number_id": agent_phone_number_id,
        "to_number": phone_number,
    }

    if metadata:
        payload["conversation_initiation_client_data"] = {
            "metadata": metadata,
        }

    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.post(
            f"{ELEVENLABS_API_BASE}/convai/twilio/outbound-call",
            headers=_headers(),
            json=payload,
        )

    result = _handle_response(response, "initiate_outbound_call")
    logger.info(
        f"Outbound call initiated to {phone_number} via agent {elevenlabs_agent_id}: "
        f"call_id={result.get('call_id', result.get('conversation_id', 'unknown'))}"
    )
    return result


def get_call_transcript(conversation_id: str) -> Dict[str, Any]:
    """
    Get transcript and details of a completed call.

    GET /v1/convai/conversations/{conversation_id}

    Called after a call ends (via webhook or polling) to:
      - Store transcript in calls table
      - Parse buying intent signals
      - Update lead interest_level

    Used by Day 6 Call Engine.
    """
    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{ELEVENLABS_API_BASE}/convai/conversations/{conversation_id}",
            headers=_headers(),
        )
    return _handle_response(response, "get_call_transcript")


def list_conversations(
    agent_id: Optional[str] = None,
    page_size: int = 30,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List all conversations (calls) for an agent.

    GET /v1/convai/conversations

    Used by the call analytics dashboard (Day 6).
    """
    params: Dict[str, Any] = {"page_size": page_size}
    if agent_id:
        params["agent_id"] = agent_id
    if cursor:
        params["cursor"] = cursor

    with httpx.Client(timeout=_TIMEOUT) as client:
        response = client.get(
            f"{ELEVENLABS_API_BASE}/convai/conversations",
            headers=_headers(),
            params=params,
        )
    return _handle_response(response, "list_conversations")


# ══════════════════════════════════════════════════════════════════════════════
# PROMPT BUILDER — generates tailored prompts for Suzuki campaigns
# ══════════════════════════════════════════════════════════════════════════════

def build_suzuki_system_prompt(
    dealership_name: str,
    campaign_name: str,
    campaign_description: Optional[str],
    car_model_name: Optional[str],
    promotion_type: Optional[str],
    language: str = "en",
    agent_name: str = "Priya",
) -> str:
    """
    Build a tailored system prompt for a Suzuki campaign.

    Real-world: Each campaign gets a custom prompt based on:
      - Which car model is being promoted (Brezza, Swift, Ertiga, etc.)
      - What promotion type (exchange bonus, new launch, EMI scheme, etc.)
      - Which language to use (English, Hindi, Telugu, etc.)

    The prompt does NOT include KB content — ElevenLabs injects that
    automatically from the linked knowledge base document.
    """
    # Language-specific greeting style
    lang_hints = {
        "hi": "Respond in Hindi (Devanagari or Roman script based on customer preference). "
               "Mix Hindi and English naturally (Hinglish) for better understanding.",
        "te": "Respond in Telugu if the customer prefers it, otherwise use English or Hindi.",
        "en": "Respond in clear, friendly Indian English.",
        "ta": "Respond in Tamil if the customer prefers it, otherwise use English.",
    }
    lang_instruction = lang_hints.get(language, lang_hints["en"])

    # Promotion-specific talking points
    promo_hints = {
        "exchange_bonus":  "Emphasize the exchange bonus amount and how easy it is to trade in their old car.",
        "new_launch":      "Highlight what's new and exciting about this model. Create curiosity.",
        "festive_offer":   "Emphasize limited-time festive discounts and special financing.",
        "test_drive":      "Focus on getting them to book a test drive. Low commitment ask.",
        "emi_scheme":      "Lead with the low monthly EMI. Make it sound affordable.",
        "corporate_offer": "Emphasize corporate pricing, fleet discounts, and GST benefits.",
        "service_camp":    "Remind them of their vehicle and offer a free service camp booking.",
    }
    promo_tip = promo_hints.get(promotion_type or "", "Share the key benefits of this offer.")

    car_context = f"The specific car being promoted is: {car_model_name}." if car_model_name else ""
    camp_desc = campaign_description or campaign_name

    prompt = f"""You are {agent_name}, a friendly and knowledgeable Suzuki sales representative calling on behalf of {dealership_name}.

ROLE:
You are making an outbound sales call to a potential customer who has shown interest in Suzuki vehicles or has been identified as a good fit for this offer.

CAMPAIGN:
{camp_desc}
{car_context}

YOUR GOAL (in order of priority):
1. Build rapport — be warm, natural, and respectful of the customer's time
2. Briefly introduce the offer or promotion (15-20 seconds max)
3. Answer any questions ONLY from your knowledge base — never guess or make up specifications, prices, or features
4. Qualify interest: ask about budget, current vehicle, timeline
5. Close with a clear next step: test drive booking, WhatsApp info sharing, or callback scheduling

LANGUAGE:
{lang_instruction}

SELLING APPROACH:
{promo_tip}

CRITICAL RULES:
- Answer ONLY from your knowledge base. If asked something not in your KB, say: "That's a great question — let me have our specialist call you back with that detail."
- Never share competitor pricing or disparage other brands
- If customer says "not interested", say "No problem! If you change your mind, please visit {dealership_name}. Have a great day!" and end the call politely
- Keep each response to 2-3 sentences maximum — this is a phone call
- Never read out the entire brochure — be conversational
- If customer asks for a test drive or showroom visit, confirm the dealership name and ask for a convenient time

DEALERSHIP: {dealership_name}
"""
    return prompt.strip()


def build_first_message(
    agent_name: str,
    dealership_name: str,
    lead_name: Optional[str],
    campaign_name: str,
    language: str = "en",
) -> str:
    """
    Build the first message the agent speaks when the call connects.

    Real-world: A good first message must:
    1. Identify who is calling and on whose behalf
    2. Get permission to continue (ask if this is a good time)
    3. Be under 15 seconds when spoken aloud

    Note: This is the SAME first_message for all leads in a campaign.
    For lead-name personalization, use ElevenLabs dynamic variables
    (set via conversation_initiation_client_data at call time — Day 6).
    """
    greeting = lead_name or "there"

    messages = {
        "en": (
            f"Hello {greeting}! This is {agent_name} calling from {dealership_name}. "
            f"I'm reaching out about {campaign_name}. "
            f"Do you have a moment to chat?"
        ),
        "hi": (
            f"Namaste {greeting}! Main {agent_name} bol rahi hoon {dealership_name} ki taraf se. "
            f"Main {campaign_name} ke baare mein aapko kuch batana chahti thi. "
            f"Kya aap ek minute baat kar sakte hain?"
        ),
    }

    return messages.get(language, messages["en"])


# ══════════════════════════════════════════════════════════════════════════════
# CONNECTIVITY TEST
# ══════════════════════════════════════════════════════════════════════════════

def test_elevenlabs_connection() -> Dict[str, Any]:
    """
    Test ElevenLabs API connectivity and key validity.

    GET /v1/user
    Returns user account info if key is valid.
    Used by the health check endpoint.
    """
    if not ELEVENLABS_API_KEY:
        return {
            "connected": False,
            "error": "ELEVENLABS_API_KEY environment variable not set",
        }

    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            response = client.get(
                f"{ELEVENLABS_API_BASE}/user",
                headers=_headers(),
            )

        if response.status_code == 200:
            user_data = response.json()
            return {
                "connected": True,
                "subscription": user_data.get("subscription", {}).get("tier", "unknown"),
                "character_count": user_data.get("subscription", {}).get("character_count", 0),
                "character_limit": user_data.get("subscription", {}).get("character_limit", 0),
            }
        else:
            return {
                "connected": False,
                "error": f"API key invalid or unauthorized (HTTP {response.status_code})",
            }

    except httpx.ConnectError:
        return {"connected": False, "error": "Cannot reach ElevenLabs API. Check internet connection."}
    except Exception as e:
        return {"connected": False, "error": str(e)}
