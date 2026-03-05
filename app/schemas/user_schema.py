import re
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from uuid import UUID
from typing import Optional
from datetime import datetime


# ── Helpers ───────────────────────────────────────────────────────────────────

PHONE_RE = re.compile(r"^\+?[1-9]\d{9,14}$")  # 10-15 digits total (E.164)


def _check_phone(v: str, field_name: str = "phone") -> str:
    v = v.strip()
    if not v:
        raise ValueError(f"{field_name} cannot be blank")
    if not PHONE_RE.match(v):
        raise ValueError(f"{field_name} must be a valid phone number (e.g. +919876543210)")
    return v


# ── Register ──────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    phone: str
    employee_id: str
    company_name: str

    # Optional profile fields at registration
    designation: Optional[str] = None
    department: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def name_not_blank(cls, v: str, info) -> str:
        v = v.strip()
        if not v:
            raise ValueError(f"{info.field_name} cannot be blank")
        if len(v) < 2:
            raise ValueError(f"{info.field_name} must be at least 2 characters")
        if not re.match(r"^[A-Za-z\s\-']+$", v):
            raise ValueError(f"{info.field_name} must contain only letters")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _check_phone(v)

    @field_validator("employee_id")
    @classmethod
    def employee_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("employee_id cannot be blank")
        if len(v) < 3:
            raise ValueError("employee_id must be at least 3 characters")
        return v.upper()

    @field_validator("company_name")
    @classmethod
    def company_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company_name cannot be blank")
        return v


# ── Login ─────────────────────────────────────────────────────────────────────

class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("password cannot be blank")
        return v


# ── Update Profile ────────────────────────────────────────────────────────────

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    bio: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def name_not_blank(cls, v: Optional[str], info) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError(f"{info.field_name} cannot be set to blank")
            if not re.match(r"^[A-Za-z\s\-']+$", v):
                raise ValueError(f"{info.field_name} must contain only letters")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _check_phone(v)
        return v


# ── Change Password ───────────────────────────────────────────────────────────

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 8:
            raise ValueError("New password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("New password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("New password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("New password must contain at least one special character")
        return v

    @model_validator(mode="after")
    def passwords_match(self) -> "ChangePasswordRequest":
        if self.new_password != self.confirm_password:
            raise ValueError("new_password and confirm_password do not match")
        return self


# ── Response ──────────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    first_name: str
    last_name: str
    phone: str
    employee_id: str
    company_name: str
    designation: Optional[str]
    department: Optional[str]
    bio: Optional[str]
    profile_picture: Optional[str]
    dealership_id: Optional[UUID]
    role: str
    is_active: bool
    is_verified: bool
    last_login_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Token ─────────────────────────────────────────────────────────────────────

class TokenRefresh(BaseModel):
    refresh_token: str

    @field_validator("refresh_token")
    @classmethod
    def token_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("refresh_token cannot be blank")
        return v