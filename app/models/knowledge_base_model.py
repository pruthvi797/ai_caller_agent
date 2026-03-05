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

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    name = Column(String(255), nullable=False)           # e.g. "March 2026 Suzuki KB"
    description = Column(Text, nullable=True)

    # ── Build state ───────────────────────────────────────────────────────────
    # draft -> building -> ready | failed
    # draft   = created, documents not yet compiled
    # building = compilation in progress
    # ready   = all documents processed, embeddings stored, ready for campaigns
    # failed  = compilation failed (check build_error)
    status = Column(String(30), nullable=False, default="draft")
    build_error = Column(Text, nullable=True)
    built_at = Column(TIMESTAMP, nullable=True)          # when status became 'ready'

    # ── Stats ─────────────────────────────────────────────────────────────────
    total_documents = Column(Integer, nullable=False, default=0)
    total_chunks = Column(Integer, nullable=False, default=0)

    # ── Soft delete ───────────────────────────────────────────────────────────
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())


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