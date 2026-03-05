import uuid
from sqlalchemy import (
    Column, String, Text, TIMESTAMP, ForeignKey,
    Boolean, Integer, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class Document(Base):
    """
    Represents an uploaded document (PDF, DOCX, image) for a dealership.

    Real-world business logic:
    - A dealership uploads their car brochures, pricing sheets, offers etc.
    - Each document is linked to the dealership (and optionally to a specific car model)
    - Documents are stored on disk under /uploads/documents/<dealership_id>/
    - After upload, the processing pipeline extracts text and splits it into chunks
    - Chunks are stored in document_chunks table and used to answer caller questions
    """

    __tablename__ = "documents"

    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ─────────────────────────────────────────────────────────────
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )

    # Optional: link to a specific car model (e.g. Swift brochure → Swift)
    car_model_id = Column(
        UUID(as_uuid=True),
        ForeignKey("car_models.car_model_id"),
        nullable=True,
        index=True
    )

    # ── File metadata ─────────────────────────────────────────────────────────
    filename = Column(String(255), nullable=False)              # original uploaded filename
    stored_filename = Column(String(255), nullable=False)       # UUID-renamed file on disk
    file_path = Column(Text, nullable=False)                    # full path on disk
    file_type = Column(String(50), nullable=False)              # pdf | docx | image | txt
    mime_type = Column(String(100), nullable=True)              # e.g. application/pdf
    file_size_bytes = Column(BigInteger, nullable=True)         # file size for display

    # ── Document classification ───────────────────────────────────────────────
    # brochure | pricing_sheet | feature_comparison | promotional_offer | spec_sheet | other
    document_type = Column(String(50), nullable=False, default="brochure")

    # ── Processing state ──────────────────────────────────────────────────────
    # pending -> processing -> processed | failed
    processing_status = Column(String(30), nullable=False, default="pending")
    processing_error = Column(Text, nullable=True)              # error message if failed
    processed_at = Column(TIMESTAMP, nullable=True)             # when processing completed

    # ── Extracted content ─────────────────────────────────────────────────────
    extracted_text = Column(Text, nullable=True)                # raw full text from doc
    chunk_count = Column(Integer, nullable=True, default=0)     # how many chunks created

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)
    deleted_at = Column(TIMESTAMP, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    uploaded_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False
    )
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())