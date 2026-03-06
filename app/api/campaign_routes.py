"""
Campaign Routes
===============

Real-world flow:
  1. Sales manager creates campaign (POST /campaigns/)
  2. Links car documents (POST /campaigns/{id}/documents/auto-link OR manual link)
  3. Creates/assigns a KB (POST /kb/, then PATCH /campaigns/{id})
  4. Uploads lead list (POST /campaigns/{id}/leads/csv)
  5. Activates campaign (PATCH /campaigns/{id} with status=active)
  6. ElevenLabs AI agent starts calling leads
"""

import csv
import io
import uuid
from datetime import datetime
from typing import Optional, List

from fastapi import (
    APIRouter, Depends, HTTPException, Query,
    UploadFile, File, BackgroundTasks
)
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.models.campaign import Campaign
from app.models.campaign_documents import CampaignDocument
from app.models.lead import Lead
from app.models.document_model import Document
from app.models.car_model import CarModel
from app.models.user import User
from app.schemas.campaign_schema import (
    CampaignCreate, CampaignUpdate, CampaignResponse, CampaignDetailResponse,
    LinkDocumentsRequest, AutoLinkRequest, CampaignDocumentResponse,
    LeadCreate, LeadUpdate, LeadResponse,
    BulkUploadResult,
    normalise_phone, validate_phone_field,
    VALID_CALL_STATUSES, VALID_INTEREST_LEVELS,
)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

MAX_CSV_SIZE_MB = 5
MAX_CSV_ROWS = 5000


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _require_dealership(current_user: User) -> None:
    if not current_user.dealership_id:  # type: ignore[truthy-function]
        raise HTTPException(
            status_code=400,
            detail="You must create a dealership first (POST /dealership/create)"
        )


def _get_campaign_or_404(campaign_id: str, dealership_id, db: Session) -> Campaign:
    c = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id,
        Campaign.dealership_id == dealership_id,
        Campaign.deleted_at.is_(None)
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


def _get_lead_or_404(lead_id: str, campaign_id: str, db: Session) -> Lead:
    lead = db.query(Lead).filter(
        Lead.lead_id == lead_id,
        Lead.campaign_id == campaign_id,
        Lead.deleted_at.is_(None)
    ).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


def _recalc_lead_stats(campaign: Campaign, db: Session) -> None:
    """Recalculate denormalised lead stat counters on campaign."""
    base = db.query(Lead).filter(
        Lead.campaign_id == campaign.campaign_id,
        Lead.deleted_at.is_(None),
        Lead.is_duplicate == False  # noqa: E712
    )
    campaign.total_leads = base.count()  # type: ignore[assignment]
    campaign.leads_called = base.filter(Lead.call_attempts > 0).count()  # type: ignore[assignment]
    campaign.leads_interested = base.filter(  # type: ignore[assignment]
        Lead.interest_level.in_(["hot", "warm"])
    ).count()
    campaign.leads_converted = base.filter(  # type: ignore[assignment]
        Lead.call_status == "converted"
    ).count()
    campaign.updated_at = datetime.utcnow()  # type: ignore[assignment]


def _check_duplicate(phone: str, dealership_id, campaign_id, db: Session) -> Optional[Lead]:
    """
    Check if a lead with this phone already exists in this dealership.
    Duplicate = same normalised phone number, same dealership, any campaign.
    """
    return db.query(Lead).filter(
        Lead.dealership_id == dealership_id,
        Lead.phone == phone,
        Lead.deleted_at.is_(None)
    ).first()


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/", response_model=CampaignResponse, status_code=201)
def create_campaign(
    body: CampaignCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new campaign.

    Real-world: Sales manager creates "March Brezza Exchange Bonus Campaign"
    targeting customers who might trade in their old car for a new Brezza.
    Status starts as 'draft' until documents + leads are linked and it's activated.
    """
    _require_dealership(current_user)

    # Validate car_model_id belongs to this dealership
    if body.car_model_id:
        car = db.query(CarModel).filter(
            CarModel.car_model_id == body.car_model_id,
            CarModel.dealership_id == current_user.dealership_id,
            CarModel.deleted_at.is_(None)
        ).first()
        if not car:
            raise HTTPException(
                status_code=404,
                detail="Car model not found in your dealership inventory"
            )

    # Prevent duplicate campaign names for same dealership
    existing = db.query(Campaign).filter(
        Campaign.dealership_id == current_user.dealership_id,
        Campaign.campaign_name == body.campaign_name.strip(),
        Campaign.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A campaign named '{body.campaign_name}' already exists. Use a unique name."
        )

    now = datetime.utcnow()
    campaign = Campaign(
        campaign_id=uuid.uuid4(),
        dealership_id=current_user.dealership_id,
        created_by=current_user.user_id,
        car_model_id=body.car_model_id,
        campaign_name=body.campaign_name.strip(),
        description=body.description,
        promotion_type=body.promotion_type,
        start_date=body.start_date,
        end_date=body.end_date,
        status="draft",
        knowledge_base_id=body.knowledge_base_id,
        daily_call_limit=body.daily_call_limit,
        calling_hours=body.calling_hours,
        language=body.language,
        internal_notes=body.internal_notes,
        total_leads=0,
        leads_called=0,
        leads_interested=0,
        leads_converted=0,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/", response_model=List[CampaignResponse])
def list_campaigns(
    status: Optional[str] = Query(None, description="Filter by status: draft|active|paused|completed|cancelled"),
    promotion_type: Optional[str] = Query(None),
    car_model_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search campaign name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List campaigns with filters.

    Real-world: Sales manager dashboard shows all active campaigns,
    filtered by car model or promotion type.
    """
    _require_dealership(current_user)

    q = db.query(Campaign).filter(
        Campaign.dealership_id == current_user.dealership_id,
        Campaign.deleted_at.is_(None)
    )
    if status:
        q = q.filter(Campaign.status == status)
    if promotion_type:
        q = q.filter(Campaign.promotion_type == promotion_type)
    if car_model_id:
        q = q.filter(Campaign.car_model_id == car_model_id)
    if search:
        q = q.filter(Campaign.campaign_name.ilike(f"%{search}%"))

    return q.order_by(Campaign.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{campaign_id}", response_model=CampaignDetailResponse)
def get_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get campaign with linked documents summary."""
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    # Fetch linked documents
    linked = db.query(CampaignDocument, Document).join(
        Document, CampaignDocument.document_id == Document.document_id
    ).filter(
        CampaignDocument.campaign_id == campaign_id
    ).all()

    linked_docs = [
        {
            "document_id": str(cd.document_id),
            "filename": doc.filename,
            "document_type": doc.document_type,
            "processing_status": doc.processing_status,
            "chunk_count": doc.chunk_count,
            "is_primary": cd.is_primary,
            "link_source": cd.link_source,
            "linked_at": cd.linked_at.isoformat() if cd.linked_at else None,
        }
        for cd, doc in linked
    ]

    result = CampaignDetailResponse.model_validate(campaign)
    result.linked_documents = linked_docs
    return result


@router.patch("/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: str,
    body: CampaignUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update campaign fields.

    Status transition rules (real-world logic):
      draft     → active    : campaign goes live, AI starts calling
      active    → paused    : temporarily stop calls (e.g. holiday)
      paused    → active    : resume
      active    → completed : manually close after campaign period ends
      any       → cancelled : permanently close
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    # Status transition validation
    if body.status:
        current_status = str(campaign.status)
        new_status = body.status
        allowed_transitions = {
            "draft":     {"active", "cancelled"},
            "active":    {"paused", "completed", "cancelled"},
            "paused":    {"active", "cancelled"},
            "completed": set(),
            "cancelled": set(),
        }
        if new_status not in allowed_transitions.get(current_status, set()):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot transition from '{current_status}' to '{new_status}'. "
                    f"Allowed: {allowed_transitions.get(current_status) or 'none (terminal state)'}"
                )
            )

        # Require at least one lead before activating
        if new_status == "active":
            lead_count = db.query(Lead).filter(
                Lead.campaign_id == campaign_id,
                Lead.deleted_at.is_(None),
                Lead.is_duplicate == False  # noqa: E712
            ).count()
            if lead_count == 0:
                raise HTTPException(
                    status_code=422,
                    detail="Cannot activate campaign with 0 leads. Add leads first."
                )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)
    campaign.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}")
def delete_campaign(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Soft-delete campaign. Leads and document links are preserved for audit trail.
    Cannot delete an active campaign — pause or complete it first.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    if campaign.status == "active":  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=422,
            detail="Cannot delete an active campaign. Pause or complete it first."
        )

    campaign.deleted_at = datetime.utcnow()  # type: ignore[assignment]
    campaign.is_active = False               # type: ignore[assignment]
    campaign.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()
    return {"message": f"Campaign '{campaign.campaign_name}' has been deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN → DOCUMENT LINKING
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{campaign_id}/documents", status_code=201)
def link_documents(
    campaign_id: str,
    body: LinkDocumentsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually link documents to a campaign.

    Real-world: Link the Brezza brochure, March pricing sheet, and
    Navratri offer image to the "March Brezza Campaign".
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    linked = []
    already_linked = []
    not_found = []

    for i, doc_id in enumerate(body.document_ids):
        # Verify document belongs to this dealership
        doc = db.query(Document).filter(
            Document.document_id == doc_id,
            Document.dealership_id == current_user.dealership_id,
            Document.deleted_at.is_(None)
        ).first()
        if not doc:
            not_found.append(str(doc_id))
            continue

        # Check already linked
        existing_link = db.query(CampaignDocument).filter(
            CampaignDocument.campaign_id == campaign_id,
            CampaignDocument.document_id == doc_id
        ).first()
        if existing_link:
            already_linked.append(str(doc_id))
            continue

        # Mark first doc as primary if requested
        is_primary = body.is_primary and i == 0

        link = CampaignDocument(
            campaign_id=uuid.UUID(campaign_id),
            document_id=doc_id,
            is_primary=is_primary,
            link_source="manual",
            linked_at=datetime.utcnow(),
            linked_by=current_user.user_id,
        )
        db.add(link)
        linked.append(str(doc_id))

    db.commit()
    return {
        "campaign_id": campaign_id,
        "linked": linked,
        "already_linked": already_linked,
        "not_found": not_found,
        "message": f"Linked {len(linked)} document(s) to campaign '{campaign.campaign_name}'"
    }


@router.post("/{campaign_id}/documents/auto-link", status_code=201)
def auto_link_documents(
    campaign_id: str,
    body: AutoLinkRequest = AutoLinkRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Auto-link all documents for the campaign's car model.

    Real-world: Campaign is for Brezza → system automatically finds and links
    all Brezza documents (brochure, pricing, offers, spec sheet).
    Saves the sales manager from manually linking each one.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    if campaign.car_model_id is None:  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=422,
            detail="Campaign has no car_model_id set. Set it first or use manual linking."
        )

    # Find all processed documents for this car model
    doc_query = db.query(Document).filter(
        Document.dealership_id == current_user.dealership_id,
        Document.car_model_id == campaign.car_model_id,
        Document.processing_status == "completed",
        Document.is_active == True,
        Document.deleted_at.is_(None)
    )
    if body.include_types:
        doc_query = doc_query.filter(Document.document_type.in_(body.include_types))

    docs = doc_query.all()
    if not docs:
        raise HTTPException(
            status_code=404,
            detail=(
                "No processed documents found for this car model. "
                "Upload and process documents via POST /documents/upload first."
            )
        )

    # Preferred link order for AI context quality
    type_priority = {
        "brochure": 1,
        "feature_comparison": 2,
        "pricing_sheet": 3,
        "promotional_offer": 4,
        "spec_sheet": 5,
        "other": 6,
    }
    docs_sorted = sorted(docs, key=lambda d: type_priority.get(str(d.document_type), 99))

    linked = []
    already_linked = []

    for i, doc in enumerate(docs_sorted):
        existing = db.query(CampaignDocument).filter(
            CampaignDocument.campaign_id == campaign_id,
            CampaignDocument.document_id == doc.document_id
        ).first()
        if existing:
            already_linked.append(str(doc.document_id))
            continue

        link = CampaignDocument(
            campaign_id=uuid.UUID(campaign_id),
            document_id=doc.document_id,
            is_primary=(i == 0),        # brochure = primary
            link_source="auto",
            linked_at=datetime.utcnow(),
            linked_by=current_user.user_id,
        )
        db.add(link)
        linked.append({
            "document_id": str(doc.document_id),
            "filename": doc.filename,
            "document_type": doc.document_type,
            "is_primary": i == 0,
        })

    db.commit()
    return {
        "campaign_id": campaign_id,
        "auto_linked": linked,
        "already_linked_count": len(already_linked),
        "message": (
            f"Auto-linked {len(linked)} document(s) for "
            f"car model {campaign.car_model_id}"
        )
    }


@router.get("/{campaign_id}/documents", response_model=List[dict])
def list_campaign_documents(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all documents linked to a campaign."""
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    rows = db.query(CampaignDocument, Document).join(
        Document, CampaignDocument.document_id == Document.document_id
    ).filter(
        CampaignDocument.campaign_id == campaign_id
    ).all()

    return [
        {
            "document_id": str(cd.document_id),
            "filename": doc.filename,
            "document_type": doc.document_type,
            "processing_status": doc.processing_status,
            "chunk_count": doc.chunk_count,
            "file_size_bytes": doc.file_size_bytes,
            "is_primary": cd.is_primary,
            "link_source": cd.link_source,
            "linked_at": cd.linked_at.isoformat() if cd.linked_at else None,
        }
        for cd, doc in rows
    ]


@router.delete("/{campaign_id}/documents/{document_id}")
def unlink_document(
    campaign_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a document link from a campaign."""
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    link = db.query(CampaignDocument).filter(
        CampaignDocument.campaign_id == campaign_id,
        CampaignDocument.document_id == document_id
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Document not linked to this campaign")

    db.delete(link)
    db.commit()
    return {"message": "Document unlinked from campaign"}


# ══════════════════════════════════════════════════════════════════════════════
# LEAD MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{campaign_id}/leads", response_model=LeadResponse, status_code=201)
def add_lead(
    campaign_id: str,
    body: LeadCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a single lead to a campaign.

    Real-world: Sales rep adds a walk-in customer who enquired about Brezza.
    Phone is normalised to E.164 and checked for duplicates across dealership.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    # Duplicate check — same phone in same dealership
    existing = _check_duplicate(body.phone, current_user.dealership_id, campaign_id, db)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "duplicate_lead",
                "message": f"A lead with phone {body.phone} already exists in your dealership.",
                "existing_lead_id": str(existing.lead_id),
                "existing_campaign_id": str(existing.campaign_id),
            }
        )

    now = datetime.utcnow()
    lead = Lead(
        lead_id=uuid.uuid4(),
        dealership_id=current_user.dealership_id,
        campaign_id=uuid.UUID(campaign_id),
        name=body.name.strip(),
        phone=body.phone,
        alternate_phone=body.alternate_phone,
        email=body.email,
        car_interest=body.car_interest,
        variant_preference=body.variant_preference,
        fuel_preference=body.fuel_preference,
        budget_min=body.budget_min,
        budget_max=body.budget_max,
        emi_preferred=body.emi_preferred,
        current_car=body.current_car,
        wants_exchange=body.wants_exchange,
        source=body.source,
        source_detail=body.source_detail,
        call_status="new",
        call_attempts=0,
        do_not_call=False,
        is_duplicate=False,
        added_by=current_user.user_id,
        agent_notes=body.agent_notes,
        created_at=now,
        updated_at=now,
    )
    db.add(lead)

    # Update campaign lead count
    _recalc_lead_stats(campaign, db)
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/{campaign_id}/leads", response_model=List[LeadResponse])
def list_leads(
    campaign_id: str,
    call_status: Optional[str] = Query(None),
    interest_level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    wants_exchange: Optional[bool] = Query(None),
    search: Optional[str] = Query(None, description="Search name or phone"),
    include_duplicates: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List leads for a campaign with filters.

    Real-world filters sales team uses:
      - call_status=new       → who hasn't been called yet
      - interest_level=hot    → prioritise hot leads for follow-up
      - wants_exchange=true   → for exchange bonus campaigns
    """
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    q = db.query(Lead).filter(
        Lead.campaign_id == campaign_id,
        Lead.deleted_at.is_(None)
    )
    if not include_duplicates:
        q = q.filter(Lead.is_duplicate == False)  # noqa: E712
    if call_status:
        q = q.filter(Lead.call_status == call_status)
    if interest_level:
        q = q.filter(Lead.interest_level == interest_level)
    if source:
        q = q.filter(Lead.source == source)
    if wants_exchange is not None:
        q = q.filter(Lead.wants_exchange == wants_exchange)
    if search:
        q = q.filter(
            (Lead.name.ilike(f"%{search}%")) |
            (Lead.phone.ilike(f"%{search}%"))
        )

    return q.order_by(Lead.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{campaign_id}/leads/{lead_id}", response_model=LeadResponse)
def get_lead(
    campaign_id: str,
    lead_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single lead."""
    _require_dealership(current_user)
    _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    return _get_lead_or_404(lead_id, campaign_id, db)


@router.patch("/{campaign_id}/leads/{lead_id}", response_model=LeadResponse)
def update_lead(
    campaign_id: str,
    lead_id: str,
    body: LeadUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update lead details or call outcome.

    Real-world: After AI call, update call_status to 'interested',
    interest_level to 'hot', set next_followup_at for human callback.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    lead = _get_lead_or_404(lead_id, campaign_id, db)

    # Phone change → re-check duplicate
    if body.phone and body.phone != str(lead.phone):
        existing = _check_duplicate(body.phone, current_user.dealership_id, campaign_id, db)
        if existing and str(existing.lead_id) != lead_id:
            raise HTTPException(
                status_code=409,
                detail=f"Phone {body.phone} is already used by lead {existing.lead_id}"
            )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(lead, field, value)
    lead.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    _recalc_lead_stats(campaign, db)
    db.commit()
    db.refresh(lead)
    return lead


@router.delete("/{campaign_id}/leads/{lead_id}")
def delete_lead(
    campaign_id: str,
    lead_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft-delete a lead."""
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)
    lead = _get_lead_or_404(lead_id, campaign_id, db)

    lead.deleted_at = datetime.utcnow()  # type: ignore[assignment]
    lead.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    _recalc_lead_stats(campaign, db)
    db.commit()
    return {"message": f"Lead '{lead.name}' has been deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# CSV BULK UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

def _parse_bool(val: Optional[str]) -> Optional[bool]:
    if not val:
        return None
    return val.strip().lower() in ("yes", "true", "1", "y")


def _parse_decimal(val: Optional[str]):
    if not val or not val.strip():
        return None
    try:
        cleaned = val.strip().replace(",", "").replace("₹", "").replace(" ", "")
        from decimal import Decimal
        return Decimal(cleaned)
    except Exception:
        return None


@router.post("/{campaign_id}/leads/csv", response_model=BulkUploadResult)
async def bulk_upload_leads(
    campaign_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk upload leads from a CSV file.

    Expected CSV columns (header row required):
      name, phone, alternate_phone, email, car_interest,
      budget_min, budget_max, current_car, wants_exchange, agent_notes

    Rules:
      - phone is required; rows without a valid phone are rejected
      - Duplicate phone (same dealership) → skipped, reported in response
      - Invalid phone format → error row, not imported
      - Max {MAX_CSV_ROWS} rows per upload
      - Max {MAX_CSV_SIZE_MB}MB file size

    Real-world: Dealership receives a lead list from a trade fair or
    purchases a bulk list from a marketing agency. Upload it here.
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    # File validation
    if file.content_type not in ("text/csv", "application/csv", "application/vnd.ms-excel",
                                  "text/plain", "application/octet-stream"):
        raise HTTPException(
            status_code=415,
            detail="File must be a CSV. Accepted content types: text/csv, text/plain"
        )

    content = await file.read()
    if len(content) > MAX_CSV_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"CSV file too large. Maximum size is {MAX_CSV_SIZE_MB}MB"
        )

    try:
        text = content.decode("utf-8-sig")  # handle BOM from Excel exports
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except Exception:
            raise HTTPException(status_code=400, detail="Could not decode CSV file. Use UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))

    # Normalise column headers: strip spaces, lowercase
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no header row")

    normalised_fields = {f.strip().lower().replace(" ", "_"): f for f in reader.fieldnames}

    def _get(row: dict, key: str) -> Optional[str]:
        """Get value from row using normalised key."""
        original_key = normalised_fields.get(key)
        if original_key:
            return row.get(original_key, "").strip() or None
        return None

    # Must have at minimum name + phone columns
    if "name" not in normalised_fields or "phone" not in normalised_fields:
        raise HTTPException(
            status_code=422,
            detail="CSV must have at minimum 'name' and 'phone' columns. "
                   f"Found columns: {list(reader.fieldnames)}"
        )

    imported = 0
    duplicates_skipped = 0
    errors = 0
    error_details = []
    duplicate_details = []
    leads_to_add = []

    # Track phones seen within this CSV to catch intra-file duplicates
    phones_in_this_upload: dict = {}

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        if row_num > MAX_CSV_ROWS + 1:
            error_details.append({
                "row": row_num,
                "error": f"CSV exceeds maximum of {MAX_CSV_ROWS} rows. Remaining rows skipped."
            })
            break

        raw_name = _get(row, "name")
        raw_phone = _get(row, "phone")

        # Required: name
        if not raw_name:
            error_details.append({"row": row_num, "phone": raw_phone, "error": "name is required"})
            errors += 1
            continue

        # Required: phone
        if not raw_phone:
            error_details.append({"row": row_num, "name": raw_name, "error": "phone is required"})
            errors += 1
            continue

        # Validate + normalise phone
        try:
            normalised_phone = normalise_phone(raw_phone)
        except ValueError as e:
            error_details.append({"row": row_num, "name": raw_name, "phone": raw_phone, "error": str(e)})
            errors += 1
            continue

        # Intra-file duplicate check
        if normalised_phone in phones_in_this_upload:
            duplicate_details.append({
                "row": row_num,
                "phone": normalised_phone,
                "name": raw_name,
                "duplicate_of_row": phones_in_this_upload[normalised_phone],
                "reason": "duplicate within this CSV file"
            })
            duplicates_skipped += 1
            continue

        # Database duplicate check
        existing = _check_duplicate(normalised_phone, current_user.dealership_id, campaign_id, db)
        if existing:
            duplicate_details.append({
                "row": row_num,
                "phone": normalised_phone,
                "name": raw_name,
                "existing_lead_id": str(existing.lead_id),
                "existing_campaign_id": str(existing.campaign_id),
                "reason": "phone already exists in dealership"
            })
            duplicates_skipped += 1
            continue

        phones_in_this_upload[normalised_phone] = row_num

        # Parse optional fields
        now = datetime.utcnow()
        lead = Lead(
            lead_id=uuid.uuid4(),
            dealership_id=current_user.dealership_id,
            campaign_id=uuid.UUID(campaign_id),
            name=raw_name.strip(),
            phone=normalised_phone,
            alternate_phone=None,   # parsed below
            email=None,
            car_interest=_get(row, "car_interest"),
            variant_preference=_get(row, "variant_preference"),
            fuel_preference=_get(row, "fuel_preference"),
            budget_min=_parse_decimal(_get(row, "budget_min")),
            budget_max=_parse_decimal(_get(row, "budget_max")),
            current_car=_get(row, "current_car"),
            wants_exchange=_parse_bool(_get(row, "wants_exchange")),
            source="csv_import",
            source_detail=str(file.filename),
            call_status="new",
            call_attempts=0,
            do_not_call=False,
            is_duplicate=False,
            added_by=current_user.user_id,
            agent_notes=_get(row, "agent_notes"),
            created_at=now,
            updated_at=now,
        )

        # Optional: validate alternate phone
        alt_phone_raw = _get(row, "alternate_phone")
        if alt_phone_raw:
            try:
                lead.alternate_phone = normalise_phone(alt_phone_raw)  # type: ignore[assignment]
            except ValueError:
                pass  # skip invalid alternate phone, don't fail row

        # Optional: validate email
        email_raw = _get(row, "email")
        if email_raw:
            import re as _re
            if _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_raw.lower()):
                lead.email = email_raw.lower()  # type: ignore[assignment]

        leads_to_add.append(lead)
        imported += 1

    # Bulk insert all valid leads
    if leads_to_add:
        db.bulk_save_objects(leads_to_add)
        db.commit()
        _recalc_lead_stats(campaign, db)
        db.commit()

    return BulkUploadResult(
        total_rows=imported + duplicates_skipped + errors,
        imported=imported,
        duplicates_skipped=duplicates_skipped,
        errors=errors,
        error_details=error_details,
        duplicate_details=duplicate_details,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN STATS
# ══════════════════════════════════════════════════════════════════════════════

def _safe_conversion_rate(converted, total) -> float:
    """
    Compute conversion rate safely without Pylance-incompatible Column casts.
    Accepts raw int or SQLAlchemy Column values — coerced via arithmetic.
    """
    try:
        t = total or 0
        c = converted or 0
        if t <= 0:
            return 0.0
        return round((c / t) * 100, 1)
    except Exception:
        return 0.0


@router.get("/{campaign_id}/stats")
def get_campaign_stats(
    campaign_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Live campaign stats for the sales manager dashboard.

    Real-world: "How many leads have been called today?
    How many are hot? How many converted?"
    """
    _require_dealership(current_user)
    campaign = _get_campaign_or_404(campaign_id, current_user.dealership_id, db)

    base = db.query(Lead).filter(
        Lead.campaign_id == campaign_id,
        Lead.deleted_at.is_(None),
        Lead.is_duplicate == False  # noqa: E712
    )

    # Status breakdown
    status_counts = {}
    for status in VALID_CALL_STATUSES:
        status_counts[status] = base.filter(Lead.call_status == status).count()

    # Interest breakdown
    interest_counts = {}
    for level in VALID_INTEREST_LEVELS:
        interest_counts[level] = base.filter(Lead.interest_level == level).count()

    # Source breakdown
    from sqlalchemy import func
    source_rows = db.query(
        Lead.source, func.count(Lead.lead_id)
    ).filter(
        Lead.campaign_id == campaign_id,
        Lead.deleted_at.is_(None),
        Lead.is_duplicate == False  # noqa: E712
    ).group_by(Lead.source).all()

    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign.campaign_name,
        "status": campaign.status,
        "start_date": str(campaign.start_date),
        "end_date": str(campaign.end_date),
        "total_leads": base.count(),
        "leads_with_exchange_interest": base.filter(Lead.wants_exchange == True).count(),  # noqa: E712
        "call_status_breakdown": status_counts,
        "interest_breakdown": interest_counts,
        "source_breakdown": {row[0]: row[1] for row in source_rows},
        "conversion_rate": _safe_conversion_rate(
            campaign.leads_converted,  # type: ignore[arg-type]
            campaign.total_leads,      # type: ignore[arg-type]
        ),
    }