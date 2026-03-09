"""
Campaign & Lead Schemas
=======================
Pydantic schemas for request validation and response serialisation.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, field_validator, model_validator


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS / ENUMS
# ══════════════════════════════════════════════════════════════════════════════

VALID_PROMOTION_TYPES = {
    "festive_offer",    # Diwali / Navratri / year-end
    "new_launch",       # New model/variant launch
    "test_drive",       # Drive showroom footfall
    "exchange_bonus",   # Trade-in old car
    "emi_scheme",       # Low EMI / 0% finance
    "corporate_offer",  # Fleet / corporate buyers
    "service_camp",     # Service follow-up for existing customers
    "general_inquiry",  # Catch-all
}

VALID_CAMPAIGN_STATUSES = {"draft", "active", "paused", "completed", "cancelled"}

VALID_LEAD_SOURCES = {
    "walk_in", "website", "csv_import", "referral", "auto_expo", "manual"
}

VALID_CALL_STATUSES = {
    "new", "called", "interested", "follow_up",
    "converted", "not_interested", "unreachable", "dnc"
}

VALID_INTEREST_LEVELS = {"hot", "warm", "cold"}

# Indian mobile: 10 digits, starts with 6-9
_INDIAN_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")


# ══════════════════════════════════════════════════════════════════════════════
# PHONE UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def normalise_phone(raw: str) -> str:
    """
    Normalise an Indian mobile number to E.164 format: +91XXXXXXXXXX

    Accepts:
      9876543210      → +919876543210
      09876543210     → +919876543210
      +919876543210   → +919876543210
      91-9876-543210  → +919876543210
    """
    digits = re.sub(r"\D", "", raw)  # strip non-digits

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if not _INDIAN_MOBILE_RE.match(digits):
        raise ValueError(
            f"'{raw}' is not a valid Indian mobile number. "
            "Must be 10 digits starting with 6-9."
        )
    return f"+91{digits}"


def validate_phone_field(v: str) -> str:
    if not v or not v.strip():
        raise ValueError("Phone number cannot be blank")
    try:
        return normalise_phone(v.strip())
    except ValueError as e:
        raise ValueError(str(e))


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class CampaignCreate(BaseModel):
    campaign_name: str
    description: Optional[str] = None
    promotion_type: str = "general_inquiry"
    car_model_id: Optional[uuid.UUID] = None
    start_date: date
    end_date: date
    knowledge_base_id: Optional[uuid.UUID] = None
    daily_call_limit: Optional[int] = None
    calling_hours: Optional[str] = "09:00-21:00"
    language: Optional[str] = "english"
    internal_notes: Optional[str] = None

    @field_validator("campaign_name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("campaign_name cannot be blank")
        if len(v) < 3:
            raise ValueError("campaign_name must be at least 3 characters")
        return v

    @field_validator("promotion_type")
    @classmethod
    def valid_promotion_type(cls, v: str) -> str:
        if v not in VALID_PROMOTION_TYPES:
            raise ValueError(
                f"promotion_type must be one of: {', '.join(sorted(VALID_PROMOTION_TYPES))}"
            )
        return v

    @field_validator("daily_call_limit")
    @classmethod
    def valid_call_limit(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("daily_call_limit must be at least 1")
        return v

    @model_validator(mode="after")
    def end_after_start(self) -> "CampaignCreate":
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValueError("end_date must be on or after start_date")
        return self


class CampaignUpdate(BaseModel):
    campaign_name: Optional[str] = None
    description: Optional[str] = None
    promotion_type: Optional[str] = None
    car_model_id: Optional[uuid.UUID] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    knowledge_base_id: Optional[uuid.UUID] = None
    daily_call_limit: Optional[int] = None
    calling_hours: Optional[str] = None
    language: Optional[str] = None
    internal_notes: Optional[str] = None

    @field_validator("campaign_name")
    @classmethod
    def name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("campaign_name cannot be blank")
        return v

    @field_validator("promotion_type")
    @classmethod
    def valid_promotion_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_PROMOTION_TYPES:
            raise ValueError(
                f"promotion_type must be one of: {', '.join(sorted(VALID_PROMOTION_TYPES))}"
            )
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CAMPAIGN_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(VALID_CAMPAIGN_STATUSES))}"
            )
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "CampaignUpdate":
        if not any(
            getattr(self, f) is not None
            for f in self.model_fields
        ):
            raise ValueError("At least one field must be provided to update")
        return self


class CampaignResponse(BaseModel):
    campaign_id: uuid.UUID
    dealership_id: uuid.UUID
    created_by: uuid.UUID
    car_model_id: Optional[uuid.UUID]
    campaign_name: str
    description: Optional[str]
    promotion_type: str
    start_date: date
    end_date: date
    status: str
    knowledge_base_id: Optional[uuid.UUID]
    daily_call_limit: Optional[int]
    calling_hours: Optional[str]
    language: Optional[str]
    total_leads: int
    leads_called: int
    leads_interested: int
    leads_converted: int
    internal_notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignDetailResponse(CampaignResponse):
    """Extended response with linked document summary."""
    linked_documents: List[dict] = []


# ══════════════════════════════════════════════════════════════════════════════
# CAMPAIGN DOCUMENT LINKING SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class LinkDocumentsRequest(BaseModel):
    """Link one or more documents to a campaign."""
    document_ids: List[uuid.UUID]
    is_primary: Optional[bool] = False    # mark the first doc as primary

    @field_validator("document_ids")
    @classmethod
    def not_empty(cls, v: List[uuid.UUID]) -> List[uuid.UUID]:
        if not v:
            raise ValueError("document_ids cannot be empty")
        return v


class AutoLinkRequest(BaseModel):
    """
    Auto-link all documents for the campaign's car model.
    System finds: brochure, pricing_sheet, feature_comparison, promotional_offer
    for the car_model_id set on the campaign.
    """
    include_types: Optional[List[str]] = None  # None = all types


class CampaignDocumentResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    document_type: str
    processing_status: str
    chunk_count: Optional[int]
    is_primary: bool
    link_source: str
    linked_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════════
# LEAD SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class LeadCreate(BaseModel):
    name: str
    phone: str
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    car_interest: Optional[str] = None
    variant_preference: Optional[str] = None
    fuel_preference: Optional[str] = None
    budget_min: Optional[Decimal] = None
    budget_max: Optional[Decimal] = None
    emi_preferred: Optional[bool] = None
    current_car: Optional[str] = None
    wants_exchange: Optional[bool] = None
    source: str = "manual"
    source_detail: Optional[str] = None
    agent_notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return validate_phone_field(v)

    @field_validator("alternate_phone")
    @classmethod
    def validate_alt_phone(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip():
            return validate_phone_field(v)
        return None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v and v.strip():
            v = v.strip().lower()
            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                raise ValueError(f"'{v}' is not a valid email address")
            return v
        return None

    @field_validator("source")
    @classmethod
    def valid_source(cls, v: str) -> str:
        if v not in VALID_LEAD_SOURCES:
            raise ValueError(
                f"source must be one of: {', '.join(sorted(VALID_LEAD_SOURCES))}"
            )
        return v

    @model_validator(mode="after")
    def budget_range_check(self) -> "LeadCreate":
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_min > self.budget_max:
                raise ValueError("budget_min cannot be greater than budget_max")
        return self


class LeadUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    car_interest: Optional[str] = None
    variant_preference: Optional[str] = None
    fuel_preference: Optional[str] = None
    budget_min: Optional[Decimal] = None
    budget_max: Optional[Decimal] = None
    emi_preferred: Optional[bool] = None
    current_car: Optional[str] = None
    wants_exchange: Optional[bool] = None
    call_status: Optional[str] = None
    interest_level: Optional[str] = None
    call_attempts: Optional[int] = None          # incremented after each call attempt
    last_called_at: Optional[datetime] = None    # timestamp of most recent call
    next_followup_at: Optional[datetime] = None
    do_not_call: Optional[bool] = None
    agent_notes: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v:
            return validate_phone_field(v)
        return v

    @field_validator("call_attempts")
    @classmethod
    def non_negative_attempts(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("call_attempts cannot be negative")
        return v

    @field_validator("call_status")
    @classmethod
    def valid_call_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_CALL_STATUSES:
            raise ValueError(
                f"call_status must be one of: {', '.join(sorted(VALID_CALL_STATUSES))}"
            )
        return v

    @field_validator("interest_level")
    @classmethod
    def valid_interest(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in VALID_INTEREST_LEVELS:
            raise ValueError(
                f"interest_level must be one of: {', '.join(sorted(VALID_INTEREST_LEVELS))}"
            )
        return v


class LeadResponse(BaseModel):
    lead_id: uuid.UUID
    dealership_id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    phone: str
    alternate_phone: Optional[str]
    email: Optional[str]
    car_interest: Optional[str]
    variant_preference: Optional[str]
    fuel_preference: Optional[str]
    budget_min: Optional[Decimal]
    budget_max: Optional[Decimal]
    emi_preferred: Optional[bool]
    current_car: Optional[str]
    wants_exchange: Optional[bool]
    source: str
    call_status: str
    interest_level: Optional[str]
    call_attempts: int
    last_called_at: Optional[datetime]
    next_followup_at: Optional[datetime]
    do_not_call: bool
    is_duplicate: bool
    duplicate_of: Optional[uuid.UUID]
    agent_notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ══════════════════════════════════════════════════════════════════════════════
# CSV BULK UPLOAD SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class CSVLeadRow(BaseModel):
    """
    Represents one row parsed from a CSV upload.
    All fields are Optional because CSV rows may be incomplete.
    Errors per row are collected and returned — not a hard failure.
    """
    row_number: int
    name: Optional[str] = None
    phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    email: Optional[str] = None
    car_interest: Optional[str] = None
    budget_min: Optional[str] = None
    budget_max: Optional[str] = None
    current_car: Optional[str] = None
    wants_exchange: Optional[str] = None
    agent_notes: Optional[str] = None


class BulkUploadResult(BaseModel):
    """Summary returned after CSV bulk upload."""
    total_rows: int
    imported: int
    duplicates_skipped: int
    errors: int
    error_details: List[dict]   # [{"row": 3, "phone": "...", "error": "..."}]
    duplicate_details: List[dict]  # [{"row": 5, "phone": "...", "existing_lead_id": "..."}]