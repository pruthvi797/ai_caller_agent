import uuid
from sqlalchemy import (
    Column, String, Text, TIMESTAMP, ForeignKey,
    Boolean, Integer
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.database import Base


class KnowledgeBase(Base):
    """
    A compiled knowledge base for a dealership campaign.

    Real-world business logic:
    - A dealership has multiple documents (brochures, pricing sheets, offers etc.)
    - Before launching an AI calling campaign, the sales manager compiles all
      relevant documents into one KnowledgeBase so the agent knows what to say
    - The KnowledgeBase is then attached to a Campaign
    - When a customer calls in, the AI agent queries this KB using vector search
      to find relevant info (e.g. "What is the price of Swift ZXI+?")
    - Multiple campaigns can share the same KB, or each can have its own

    DB columns match the migration in alembic/versions/migration_day3.py.
    Do NOT add columns here without a corresponding Alembic migration.
    """

    __tablename__ = "knowledge_bases"

    kb_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ── Ownership ─────────────────────────────────────────────────────────────
    dealership_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dealerships.dealership_id"),
        nullable=False,
        index=True
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # ── Compiled content ──────────────────────────────────────────────────────
    # The full structured text fed to the AI agent after compilation
    compiled_content = Column(Text, nullable=True)

    # JSON arrays stored as text: list of document_ids / car_model_ids used
    source_document_ids = Column(Text, nullable=True)
    car_model_ids = Column(Text, nullable=True)

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_chunks = Column(Integer, nullable=True, server_default="0")
    word_count = Column(Integer, nullable=True)

    # ── Build state ───────────────────────────────────────────────────────────
    # draft → compiling → ready | failed
    status = Column(String(30), nullable=False, server_default="draft")
    compile_error = Column(Text, nullable=True)   # populated when status=failed

    # ── ElevenLabs integration (Day 5) ────────────────────────────────────────
    elevenlabs_kb_id = Column(String(255), nullable=True)
    last_synced_at = Column(TIMESTAMP, nullable=True)

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, server_default="true")

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now(), onupdate=func.now())


class KnowledgeBaseDocument(Base):
    """
    Many-to-many join: which documents are part of which knowledge base.
    """

    __tablename__ = "knowledge_base_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kb_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_bases.kb_id"),
        nullable=False,
        index=True
    )

    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.document_id"),
        nullable=False
    )

    added_at = Column(TIMESTAMP, server_default=func.now())