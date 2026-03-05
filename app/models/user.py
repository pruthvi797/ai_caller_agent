import uuid
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Boolean, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Auth ──────────────────────────────────────────────────────────────────
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)

    # ── Identity ──────────────────────────────────────────────────────────────
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=False)
    employee_id = Column(String(50), unique=True, nullable=False, index=True)
    company_name = Column(String(255), nullable=False)

    # ── Profile ───────────────────────────────────────────────────────────────
    profile_picture = Column(Text, nullable=True)       # URL / file path
    designation = Column(String(100), nullable=True)    # e.g. "Sales Manager"
    department = Column(String(100), nullable=True)     # e.g. "Operations"
    bio = Column(Text, nullable=True)

    # ── Dealership link ───────────────────────────────────────────────────────
    # Nullable — user creates dealership manually after registration
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=True
    )

    # ── Access control ────────────────────────────────────────────────────────
    role = Column(String(50), nullable=False, default="admin")  # admin | manager | agent
    permissions = Column(Text, nullable=True)                   # JSON string for granular perms
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)

    # ── Security / session ────────────────────────────────────────────────────
    last_login_at = Column(TIMESTAMP, nullable=True)
    password_changed_at = Column(TIMESTAMP, nullable=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(TIMESTAMP, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
    deleted_at = Column(TIMESTAMP, nullable=True)   # soft-delete support