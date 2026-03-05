import uuid
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey, Boolean, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Dealership(Base):
    __tablename__ = "dealerships"

    dealership_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ─────────────────────────────────────────────────────────────
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)

    # ── Core identity ─────────────────────────────────────────────────────────
    name = Column(String(255), nullable=False)
    brand = Column(String(100), nullable=False, default="Suzuki")   # e.g. Suzuki, Toyota
    registration_number = Column(String(100), nullable=True, unique=True)  # business reg no.
    gst_number = Column(String(50), nullable=True, unique=True)

    # ── Location ──────────────────────────────────────────────────────────────
    location = Column(String(255), nullable=False)          # city / area
    showroom_address = Column(Text, nullable=False)         # full street address
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False, default="India")
    pincode = Column(String(20), nullable=True)
    latitude = Column(Numeric(10, 7), nullable=True)        # for map integrations
    longitude = Column(Numeric(10, 7), nullable=True)

    # ── Contact ───────────────────────────────────────────────────────────────
    contact_phone = Column(String(20), nullable=False)
    alternate_phone = Column(String(20), nullable=True)
    contact_email = Column(String(255), nullable=True)
    website_url = Column(String(500), nullable=True)

    # ── Branding ──────────────────────────────────────────────────────────────
    logo = Column(Text, nullable=True)                      # file path or URL
    banner_image = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    # ── Business details ──────────────────────────────────────────────────────
    established_year = Column(String(4), nullable=True)
    total_employees = Column(String(10), nullable=True)
    monthly_target_calls = Column(String(10), nullable=True)  # expected call volume

    # ── Status ────────────────────────────────────────────────────────────────
    # active | suspended | closed
    status = Column(String(20), nullable=False, default="active")
    is_verified = Column(Boolean, nullable=False, default=False)  # admin-verified dealership
    closed_at = Column(TIMESTAMP, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False)
    deleted_at = Column(TIMESTAMP, nullable=True)   # soft-delete support