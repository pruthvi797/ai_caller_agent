import re
from pydantic import BaseModel, EmailStr, field_validator, AnyHttpUrl
from uuid import UUID
from typing import Optional
from datetime import datetime
from decimal import Decimal


# ── Helpers ───────────────────────────────────────────────────────────────────

PHONE_RE = re.compile(r"^\+?[1-9]\d{9,14}$")  # 10-15 digits total (E.164)
PIN_RE = re.compile(r"^\d{4,10}$")


def _check_phone(v: str, field_name: str = "phone") -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be blank")
    if not PHONE_RE.match(v):
        raise ValueError(f"{field_name} must be a valid phone number (e.g. +919876543210)")
    return v


# ── Create ────────────────────────────────────────────────────────────────────

class DealershipCreate(BaseModel):
    # Required
    name: str
    brand: str
    location: str
    showroom_address: str
    city: str
    state: str
    contact_phone: str

    # Optional
    country: Optional[str] = "India"
    pincode: Optional[str] = None
    registration_number: Optional[str] = None
    gst_number: Optional[str] = None
    alternate_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    website_url: Optional[str] = None
    description: Optional[str] = None
    established_year: Optional[str] = None
    total_employees: Optional[str] = None
    monthly_target_calls: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Dealership name cannot be blank")
        if len(v) < 3:
            raise ValueError("Dealership name must be at least 3 characters")
        return v

    @field_validator("brand")
    @classmethod
    def brand_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Brand cannot be blank")
        return v

    @field_validator("location", "city", "state")
    @classmethod
    def location_fields_not_blank(cls, v: str, info) -> str:
        v = v.strip()
        if not v:
            raise ValueError(f"{info.field_name} cannot be blank")
        return v

    @field_validator("showroom_address")
    @classmethod
    def address_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("showroom_address cannot be blank")
        if len(v) < 10:
            raise ValueError("showroom_address must be at least 10 characters (provide full address)")
        return v

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, v: str) -> str:
        return _check_phone(v, "contact_phone")

    @field_validator("alternate_phone")
    @classmethod
    def validate_alternate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            return _check_phone(v.strip(), "alternate_phone")
        return None

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not PIN_RE.match(v):
                raise ValueError("pincode must be 4–10 digits")
        return v

    @field_validator("gst_number")
    @classmethod
    def validate_gst(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip().upper()
            # Standard Indian GST: 15 chars alphanumeric
            if v and not re.match(r"^[0-9A-Z]{15}$", v):
                raise ValueError("gst_number must be a valid 15-character GST number")
        return v

    @field_validator("established_year")
    @classmethod
    def validate_year(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not re.match(r"^\d{4}$", v):
                raise ValueError("established_year must be a 4-digit year (e.g. 2010)")
            year = int(v)
            if year < 1900 or year > 2100:
                raise ValueError("established_year must be between 1900 and 2100")
        return v

    @field_validator("website_url")
    @classmethod
    def validate_website(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v and not re.match(r"^https?://", v):
                raise ValueError("website_url must start with http:// or https://")
        return v

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and not (-90 <= float(v) <= 90):
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and not (-180 <= float(v) <= 180):
            raise ValueError("longitude must be between -180 and 180")
        return v


# ── Update ────────────────────────────────────────────────────────────────────

class DealershipUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    location: Optional[str] = None
    showroom_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    registration_number: Optional[str] = None
    gst_number: Optional[str] = None
    contact_phone: Optional[str] = None
    alternate_phone: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    website_url: Optional[str] = None
    description: Optional[str] = None
    established_year: Optional[str] = None
    total_employees: Optional[str] = None
    monthly_target_calls: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name cannot be set to blank")
        return v

    @field_validator("contact_phone")
    @classmethod
    def validate_contact_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _check_phone(v, "contact_phone")
        return v

    @field_validator("showroom_address")
    @classmethod
    def address_not_blank(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("showroom_address cannot be set to blank")
            if len(v) < 10:
                raise ValueError("showroom_address must be at least 10 characters")
        return v

    @field_validator("established_year")
    @classmethod
    def validate_year(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not re.match(r"^\d{4}$", v):
                raise ValueError("established_year must be a 4-digit year")
        return v

    @field_validator("website_url")
    @classmethod
    def validate_website(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if v and not re.match(r"^https?://", v):
                raise ValueError("website_url must start with http:// or https://")
        return v


# ── Response ──────────────────────────────────────────────────────────────────

class DealershipResponse(BaseModel):
    dealership_id: UUID
    user_id: UUID
    name: str
    brand: str
    registration_number: Optional[str]
    gst_number: Optional[str]
    location: str
    showroom_address: str
    city: str
    state: str
    country: str
    pincode: Optional[str]
    latitude: Optional[Decimal]
    longitude: Optional[Decimal]
    contact_phone: str
    alternate_phone: Optional[str]
    contact_email: Optional[str]
    website_url: Optional[str]
    logo: Optional[str]
    banner_image: Optional[str]
    description: Optional[str]
    established_year: Optional[str]
    total_employees: Optional[str]
    monthly_target_calls: Optional[str]
    status: str
    is_verified: bool
    closed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}