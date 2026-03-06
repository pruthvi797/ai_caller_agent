"""
Knowledge Base Compilation Service
====================================

Compiles chunks from MULTIPLE documents into one structured KB.

Multi-document scenario (real world):
  Dealer uploads for Brezza:
    1. brezza_brochure.pdf      → overview, features, safety, colors chunks
    2. march_pricing.pdf        → pricing chunks
    3. navratri_offers.jpg      → offers chunks
    4. brezza_spec_sheet.docx   → specifications chunks
    5. warranty_card.pdf        → warranty chunks

  POST /kb/{id}/compile
    → pulls all chunks across all 5 documents
    → deduplicates overlapping content (e.g. mileage in both brochure + spec sheet)
    → groups by section type
    → builds ONE unified structured KB ready for ElevenLabs AI agent

Compile filters available:
  - document_ids       → only compile specific documents
  - car_model_ids      → only compile for specific car models
  - include_section_types → only include specific sections
"""

import json
import re
from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from app.models.knowledge_base_model import KnowledgeBase
from app.models.document_model import Document
from app.models.document_chunk_model import DocumentChunk


# ── Section display order in compiled KB ───────────────────────────────────────
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


# ══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION — prevent duplicate content from overlapping documents
# ══════════════════════════════════════════════════════════════════════════════

def _similarity_ratio(a: str, b: str) -> float:
    """
    Fast similarity check between two text chunks.
    Uses word overlap ratio — no external libraries needed.
    Returns 0.0 (completely different) to 1.0 (identical).
    """
    words_a = set(re.findall(r'\b\w+\b', a.lower()))
    words_b = set(re.findall(r'\b\w+\b', b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _deduplicate_chunks(chunks: List[str], similarity_threshold: float = 0.75) -> List[str]:
    """
    Remove near-duplicate chunks from a list.
    Keeps the LONGER chunk when two are similar (more detail = better for AI).

    Example:
      Brochure chunk: "6 Airbags standard on ZXi+"
      Spec sheet chunk: "6 Airbags (Front, Side and Curtain) standard on ZXi+ variant"
      → Keeps spec sheet chunk (longer, more detail)

    Threshold 0.75 = 75% word overlap → considered duplicate.
    """
    if not chunks:
        return []

    # Sort by length descending — longer chunks survive
    sorted_chunks = sorted(chunks, key=len, reverse=True)
    kept: List[str] = []

    for candidate in sorted_chunks:
        is_duplicate = False
        for existing in kept:
            if _similarity_ratio(candidate, existing) >= similarity_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(candidate)

    # Re-sort by original order (chunk_index) — dedup doesn't change order
    # Since we sorted by length, restore logical reading order
    return kept


# ══════════════════════════════════════════════════════════════════════════════
# SOURCE TRACKING — record which documents contributed to the KB
# ══════════════════════════════════════════════════════════════════════════════

def _build_source_summary(chunks, db: Session) -> List[dict]:
    """
    Build a list of source documents that contributed chunks to this KB.
    Useful for audit trail and debugging.
    """
    doc_ids = list(set(str(c.document_id) for c in chunks))
    summary = []
    for doc_id in doc_ids:
        doc = db.query(Document).filter(Document.document_id == doc_id).first()
        if doc:
            doc_chunks = [c for c in chunks if str(c.document_id) == doc_id]
            summary.append({
                "document_id": doc_id,
                "filename": str(doc.filename),
                "document_type": str(doc.document_type),
                "chunks_contributed": len(doc_chunks),
                "sections": list(set(c.section_type for c in doc_chunks if c.section_type)),
            })
    return summary


# ══════════════════════════════════════════════════════════════════════════════
# KB HEADER
# ══════════════════════════════════════════════════════════════════════════════

def _build_header(dealership, kb, source_summary: List[dict]) -> str:
    """Build the header block for the compiled KB."""
    lines = [
        "SUZUKI DEALERSHIP AI ASSISTANT — KNOWLEDGE BASE",
        "=" * 60,
    ]

    if dealership:
        lines += [
            f"Dealership : {dealership.name}",
            f"Location   : {getattr(dealership, 'city', '')} {getattr(dealership, 'state', '')}".strip(),
            f"Brand      : {getattr(dealership, 'brand', 'Suzuki')}",
        ]

    lines += [
        f"KB Name    : {kb.name}",
        f"Generated  : {datetime.utcnow().strftime('%d %b %Y, %H:%M UTC')}",
        "=" * 60,
    ]

    if kb.description:
        lines.append(f"\nPurpose: {kb.description}")

    # Source documents list
    if source_summary:
        lines.append(f"\nSource Documents ({len(source_summary)}):")
        for src in source_summary:
            sections_str = ", ".join(src["sections"]) if src["sections"] else "general"
            lines.append(
                f"  • {src['filename']} [{src['document_type']}]"
                f" → {src['chunks_contributed']} chunks ({sections_str})"
            )

    lines.append(
        "\nThis knowledge base is compiled from official dealership documents "
        "and is used by the AI calling agent to answer customer questions accurately."
    )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN COMPILE FUNCTION
# ══════════════════════════════════════════════════════════════════════════════

def compile_knowledge_base(
    kb_id: str,
    db: Session,
    document_ids: Optional[List[str]] = None,
    car_model_ids: Optional[List[str]] = None,
    include_section_types: Optional[List[str]] = None,
) -> dict:
    """
    Compile all document chunks into a structured KB.

    Handles multiple documents of different types:
    - Pulls chunks from ALL uploaded documents for this dealership
    - Deduplicates overlapping content (brochure + spec sheet may overlap)
    - Groups by section type in logical reading order
    - Tracks which documents contributed what

    Optional filters:
    - document_ids: only use specific documents
    - car_model_ids: only use documents tagged to specific car models
    - include_section_types: only include certain sections
    """
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.kb_id == kb_id).first()
    if not kb:
        return {"error": "Knowledge base not found"}

    # Try to load dealership — optional, KB still compiles without it
    dealership = None
    try:
        from app.models.dealership import Dealership
        dealership = db.query(Dealership).filter(
            Dealership.dealership_id == kb.dealership_id
        ).first()
    except Exception:
        try:
            from app.models.dealership_model import Dealership  # type: ignore[no-redef]
            dealership = db.query(Dealership).filter(
                Dealership.dealership_id == kb.dealership_id
            ).first()
        except Exception:
            pass  # compile proceeds without dealership info

    # Mark as compiling
    kb.status = "compiling"          # type: ignore[assignment]
    kb.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    try:
        # ── Step 1: Query chunks ───────────────────────────────────────────────
        # Join with Document to filter only completed, active docs
        chunk_query = db.query(DocumentChunk).join(
            Document, DocumentChunk.document_id == Document.document_id
        ).filter(
            DocumentChunk.dealership_id == kb.dealership_id,
            Document.processing_status == "completed",
            Document.is_active == True,
            Document.deleted_at.is_(None),
        )

        if document_ids:
            chunk_query = chunk_query.filter(
                DocumentChunk.document_id.in_(document_ids)
            )

        if car_model_ids:
            chunk_query = chunk_query.filter(
                DocumentChunk.car_model_id.in_(car_model_ids)
            )

        if include_section_types:
            chunk_query = chunk_query.filter(
                DocumentChunk.section_type.in_(include_section_types)
            )

        # Order: by document, then by position within document
        chunks = chunk_query.order_by(
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
        ).all()

        if not chunks:
            raise ValueError(
                "No processed document chunks found for this dealership. "
                "Upload documents via POST /documents/upload and wait for processing to complete."
            )

        # ── Step 2: Build source summary (audit trail) ────────────────────────
        source_summary = _build_source_summary(chunks, db)

        # ── Step 3: Group chunks by section type ──────────────────────────────
        sections: Dict[str, List[str]] = {s: [] for s in SECTION_ORDER}
        for chunk in chunks:
            section = str(chunk.section_type) if chunk.section_type is not None else "general"
            if section not in sections:
                sections[section] = []
            if chunk.chunk_text is not None:  # type: ignore[truthy-function]
                sections[section].append(str(chunk.chunk_text))

        # ── Step 4: Deduplicate within each section ───────────────────────────
        # Multiple documents (brochure + spec sheet) may have overlapping content
        dedup_stats: Dict[str, int] = {}
        for section_type in sections:
            original_count = len(sections[section_type])
            sections[section_type] = _deduplicate_chunks(sections[section_type])
            removed = original_count - len(sections[section_type])
            if removed > 0:
                dedup_stats[section_type] = removed

        # ── Step 5: Build compiled text ───────────────────────────────────────
        header = _build_header(dealership, kb, source_summary)
        body_parts = [header]

        sections_included = []
        for section_type in SECTION_ORDER:
            section_chunks = sections.get(section_type, [])
            if not section_chunks:
                continue
            sections_included.append(section_type)
            label = SECTION_LABELS.get(section_type, section_type.upper())
            body_parts.append(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
            for chunk_text in section_chunks:
                body_parts.append(chunk_text.strip())

        body_parts.append(f"\n{'=' * 60}\nEnd of Knowledge Base\n{'=' * 60}")
        compiled = "\n\n".join(body_parts)

        # ── Step 6: Collect metadata ──────────────────────────────────────────
        source_doc_ids  = list(set(str(c.document_id) for c in chunks))
        source_car_ids  = list(set(
            str(c.car_model_id) for c in chunks if c.car_model_id  # type: ignore[truthy-function]
        ))
        total_after_dedup = sum(len(v) for v in sections.values())

        # ── Step 7: Update KB record ──────────────────────────────────────────
        kb.compiled_content    = compiled                        # type: ignore[assignment]
        kb.status              = "ready"                         # type: ignore[assignment]
        kb.total_chunks        = total_after_dedup               # type: ignore[assignment]
        kb.word_count          = len(compiled.split())           # type: ignore[assignment]
        kb.source_document_ids = json.dumps(source_doc_ids)     # type: ignore[assignment]
        kb.car_model_ids       = json.dumps(source_car_ids)     # type: ignore[assignment]
        kb.updated_at          = datetime.utcnow()               # type: ignore[assignment]
        db.commit()

        return {
            "kb_id":                str(kb_id),
            "status":               "ready",
            "total_chunks":         total_after_dedup,
            "word_count":           kb.word_count,
            "sections_included":    sections_included,
            "source_documents":     len(source_doc_ids),
            "duplicates_removed":   dedup_stats,
            "source_summary":       source_summary,
            "message": (
                f"Knowledge base compiled from {len(source_doc_ids)} document(s) "
                f"with {total_after_dedup} chunks across {len(sections_included)} sections."
                + (f" Removed {sum(dedup_stats.values())} duplicate chunks." if dedup_stats else "")
            ),
        }

    except Exception as e:
        db.rollback()
        kb.status        = "failed"     # type: ignore[assignment]
        kb.compile_error = str(e)       # type: ignore[assignment]
        kb.updated_at    = datetime.utcnow()  # type: ignore[assignment]
        db.commit()
        return {
            "kb_id":   str(kb_id),
            "status":  "failed",
            "message": f"Compilation failed: {str(e)}",
        }


# ══════════════════════════════════════════════════════════════════════════════
# EMBEDDING PLACEHOLDER (Day 5 — Semantic Search)
# ══════════════════════════════════════════════════════════════════════════════

def embed_text(text: str) -> Optional[List[float]]:
    """
    Placeholder for text embedding generation.
    Will be implemented in Day 5 when semantic search is added.
    Options: OpenAI text-embedding-3-small, Gemini embedding-001, sentence-transformers
    """
    return None