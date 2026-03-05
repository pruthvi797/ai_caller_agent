import uuid
from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class DocumentChunk(Base):
    """
    A single chunk of text extracted from a document.

    Why chunk instead of storing full text?
    - AI agents have token limits — we retrieve only the relevant chunks per query
    - Chunking by section (pricing, features, safety) allows precise retrieval
    - Each chunk can be individually embedded for semantic search

    Real-world example:
      Swift brochure → 8 chunks:
        [0] Overview & highlights
        [1] Engine & performance specs
        [2] Safety features (airbags, ABS, NCAP)
        [3] Interior features (touchscreen, AC, sunroof)
        [4] Exterior features (alloys, LED lights)
        [5] Pricing & variants table
        [6] EMI & finance options
        [7] Warranty & service info
    """
    __tablename__ = "document_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Parent relationships ───────────────────────────────────────────────────
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.document_id"),
        nullable=False,
        index=True
    )

    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )

    # Optional: directly link to car model for targeted retrieval
    car_model_id = Column(
        UUID(as_uuid=True),
        ForeignKey("car_models.car_model_id"),
        nullable=True,
        index=True
    )

    # ── Chunk content ─────────────────────────────────────────────────────────
    chunk_index = Column(Integer, nullable=False)       # position within document (0-based)
    chunk_text = Column(Text, nullable=False)           # the actual extracted text

    # Section label — auto-detected by parser
    # e.g. pricing | features | safety | specifications | overview | warranty | offers
    section_type = Column(String(50), nullable=True)

    # Character count (for token estimation)
    char_count = Column(Integer, nullable=True)

    # ── Vector embedding (pgvector) ───────────────────────────────────────────
    # Stored as Text (JSON array) now — swap to Vector(384) when pgvector ready
    # Used for semantic similarity search: "which car has the best mileage?"
    embedding = Column(Text, nullable=True)

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, server_default=func.now(), nullable=False)