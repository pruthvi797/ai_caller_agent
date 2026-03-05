"""
Knowledge Base Compilation Service

Real-world purpose:
  The ElevenLabs AI agent needs a structured text context to answer
  customer questions during calls. This service compiles document chunks
  into a clean, structured knowledge base document.

  Example compiled KB structure:
  ================================
  DEALERSHIP: Prudhvi Suzuki Motors, Hyderabad
  KNOWLEDGE BASE: Swift 2024 Campaign KB
  Generated: 2024-03-04

  == OVERVIEW ==
  The Maruti Suzuki Swift 2024 is a premium hatchback...

  == PRICING ==
  Swift LXI: ₹6.49 Lakh (ex-showroom)
  Swift VXI: ₹7.19 Lakh
  Swift ZXI: ₹8.42 Lakh
  Swift ZXI+: ₹8.99 Lakh

  == SPECIFICATIONS ==
  Engine: 1.2L DualJet K-Series
  Mileage: 24.8 kmpl (MT)
  ...

  == SAFETY ==
  6 airbags standard on ZXI+
  NCAP Rating: 3-Star
  ...
  ================================

  This structured text is then either:
  a) Sent directly as system prompt context to ElevenLabs
  b) Stored as a file and referenced via ElevenLabs KB API
"""

import json
import re
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.knowledge_base_model import KnowledgeBase
from app.models.document_model import Document
from app.models.document_chunk_model import DocumentChunk
from app.models.dealership import Dealership


# Section display order in the compiled KB
SECTION_ORDER = [
    "overview",
    "specifications",
    "pricing",
    "offers",
    "features",
    "safety",
    "colors",
    "warranty",
    "general",
]

SECTION_LABELS = {
    "overview":       "OVERVIEW",
    "specifications": "TECHNICAL SPECIFICATIONS",
    "pricing":        "PRICING & VARIANTS",
    "offers":         "CURRENT OFFERS & PROMOTIONS",
    "features":       "FEATURES & TECHNOLOGY",
    "safety":         "SAFETY",
    "colors":         "AVAILABLE COLORS",
    "warranty":       "WARRANTY & SERVICE",
    "general":        "ADDITIONAL INFORMATION",
}


def compile_knowledge_base(kb_id: str, db: Session,
                             document_ids: Optional[List[str]] = None,
                             car_model_ids: Optional[List[str]] = None,
                             include_section_types: Optional[List[str]] = None) -> dict:
    """
    Compile a knowledge base from document chunks.

    Steps:
    1. Load all relevant document chunks for this dealership
    2. Group chunks by section type
    3. Build structured text with clear section headers
    4. Store compiled content + metadata on the KB record
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.kb_id == kb_id).first()
    if not kb:
        return {"error": "Knowledge base not found"}

    dealership = db.query(Dealership).filter(
        Dealership.dealership_id == kb.dealership_id
    ).first()

    # Mark as compiling
    kb.status = "compiling"  # type: ignore[assignment]
    kb.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    try:
        # ── Step 1: Build chunk query ─────────────────────────────────────────
        chunk_query = db.query(DocumentChunk).join(
            Document, DocumentChunk.document_id == Document.document_id
        ).filter(
            DocumentChunk.dealership_id == kb.dealership_id,
            Document.processing_status == "completed",
            Document.is_active == True,
            Document.deleted_at.is_(None),
        )

        # Filter by specific documents if provided
        if document_ids:
            chunk_query = chunk_query.filter(
                DocumentChunk.document_id.in_(document_ids)
            )

        # Filter by car models if provided
        if car_model_ids:
            chunk_query = chunk_query.filter(
                DocumentChunk.car_model_id.in_(car_model_ids)
            )

        # Filter by section type if specified
        if include_section_types:
            chunk_query = chunk_query.filter(
                DocumentChunk.section_type.in_(include_section_types)
            )

        chunks = chunk_query.order_by(
            DocumentChunk.document_id,
            DocumentChunk.chunk_index
        ).all()

        if not chunks:
            raise ValueError(
                "No processed document chunks found. "
                "Upload and process documents first via POST /documents/upload"
            )

        # ── Step 2: Group by section type ─────────────────────────────────────
        sections: dict = {s: [] for s in SECTION_ORDER}
        for chunk in chunks:
            section = chunk.section_type or "general"
            if section not in sections:
                sections[section] = []
            sections[section].append(chunk.chunk_text)

        # ── Step 3: Build compiled text ───────────────────────────────────────
        header = _build_header(dealership, kb)
        body_parts = [header]

        for section_type in SECTION_ORDER:
            section_chunks = sections.get(section_type, [])
            if not section_chunks:
                continue
            label = SECTION_LABELS.get(section_type, section_type.upper())
            body_parts.append(f"\n{'='*60}\n{label}\n{'='*60}")
            for chunk_text in section_chunks:
                body_parts.append(chunk_text.strip())

        body_parts.append(f"\n{'='*60}\nEnd of Knowledge Base\n{'='*60}")
        compiled = "\n\n".join(body_parts)

        # ── Step 4: Collect source document IDs ───────────────────────────────
        source_doc_ids = list(set(str(c.document_id) for c in chunks))
        source_car_ids = list(set(str(c.car_model_id) for c in chunks if c.car_model_id))  # type: ignore[truthy-function]

        # ── Step 5: Update KB record ──────────────────────────────────────────
        kb.compiled_content = compiled  # type: ignore[assignment]
        kb.status = "ready"  # type: ignore[assignment]
        kb.total_chunks = len(chunks)  # type: ignore[assignment]
        kb.word_count = len(compiled.split())  # type: ignore[assignment]
        kb.source_document_ids = json.dumps(source_doc_ids)  # type: ignore[assignment]
        kb.car_model_ids = json.dumps(source_car_ids)  # type: ignore[assignment]
        kb.updated_at = datetime.utcnow()  # type: ignore[assignment]
        db.commit()

        return {
            "kb_id": str(kb_id),
            "status": "ready",
            "total_chunks": len(chunks),
            "word_count": kb.word_count,
            "sections_included": [s for s in SECTION_ORDER if sections.get(s)],
            "message": f"Knowledge base compiled successfully with {len(chunks)} chunks"
        }

    except Exception as e:
        db.rollback()
        kb.status = "failed"  # type: ignore[assignment]
        kb.compile_error = str(e)  # type: ignore[assignment]
        kb.updated_at = datetime.utcnow()  # type: ignore[assignment]
        db.commit()
        return {
            "kb_id": str(kb_id),
            "status": "failed",
            "message": f"Compilation failed: {str(e)}"
        }


def _build_header(dealership, kb) -> str:
    """Build the header block for the compiled KB."""
    lines = [
        "SUZUKI DEALERSHIP AI ASSISTANT — KNOWLEDGE BASE",
        "=" * 60,
        f"Dealership : {dealership.name if dealership else 'Unknown'}",
        f"Location   : {dealership.city + ', ' + dealership.state if dealership else ''}",
        f"Brand      : {dealership.brand if dealership else 'Suzuki'}",
        f"KB Name    : {kb.name}",
        f"Generated  : {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')}",
        "=" * 60,
    ]
    if kb.description:
        lines.append(f"\nPurpose: {kb.description}")
    lines.append(
        "\nThis knowledge base is used by the AI calling agent to answer "
        "customer questions accurately based on official brochure data."
    )
    return "\n".join(lines)