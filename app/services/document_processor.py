"""
Document Processing Service

Real-world pipeline:
  1. File uploaded → saved to disk → Document record created (status: pending)
  2. process_document() called → extracts raw text based on file type
  3. Text is cleaned (whitespace, headers/footers removed)
  4. Text is split into semantic chunks (by section heading or fixed size)
  5. Each chunk classified by section type (pricing, features, safety, etc.)
  6. Chunks saved → Document status updated to completed

Why this matters for AI calling:
  When a customer asks "What are the safety features of Swift?",
  the agent retrieves the 'safety' section chunk → answers accurately
  instead of hallucinating or giving generic info.
"""

import os
import re
import uuid
from typing import List, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.document_model import Document
from app.models.document_chunk_model import DocumentChunk


# ── Section detection keywords ─────────────────────────────────────────────────
# Maps section type to keywords that indicate that section in a brochure
SECTION_KEYWORDS = {
    "pricing":        ["price", "ex-showroom", "on-road", "emi", "finance", "cost", "lakh", "₹"],
    "features":       ["feature", "infotainment", "touchscreen", "sunroof", "camera", "cruise", "climate"],
    "safety":         ["safety", "airbag", "abs", "esp", "ncap", "rating", "brake", "seatbelt", "collision"],
    "specifications": ["engine", "displacement", "cc", "bhp", "torque", "mileage", "kmpl", "transmission",
                       "wheelbase", "ground clearance", "boot space", "fuel tank"],
    "overview":       ["overview", "introduction", "about", "highlights", "key points", "why choose"],
    "warranty":       ["warranty", "service", "maintenance", "annual", "years", "km coverage"],
    "offers":         ["offer", "discount", "cashback", "exchange", "bonus", "festive", "promotion", "scheme"],
    "colors":         ["color", "colour", "shade", "arctic", "metallic", "pearl", "premium"],
}

CHUNK_SIZE = 800        # target characters per chunk
CHUNK_OVERLAP = 100     # overlap between chunks to preserve context


# ── PDF Extraction ─────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract full text from a PDF file.
    Uses PyMuPDF (fitz) as primary — falls back to pdfplumber if needed.
    """
    try:
        import fitz  # PyMuPDF
        text_parts = []
        doc = fitz.open(file_path)
        pages = list(doc)  # type: ignore[arg-type]
        for page_num, page in enumerate(pages, 1):
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(f"[Page {page_num}]\n{page_text}")
        doc.close()
        return "\n\n".join(text_parts)
    except ImportError:
        pass  # fall through to pdfplumber

    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"[Page {page_num}]\n{page_text}")
        return "\n\n".join(text_parts)
    except ImportError:
        raise RuntimeError(
            "No PDF parser available. Install PyMuPDF: pip install pymupdf "
            "or pdfplumber: pip install pdfplumber"
        )


# ── DOCX Extraction ────────────────────────────────────────────────────────────

def extract_text_from_docx(file_path: str) -> str:
    """
    Extract text from a .docx file preserving paragraph structure.
    Uses python-docx.
    """
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(file_path)
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                # Preserve headings with a marker
                style_name = (para.style.name or "") if para.style else ""
                if style_name.startswith("Heading"):
                    paragraphs.append(f"\n## {text}\n")
                else:
                    paragraphs.append(text)
        # Also extract tables (pricing tables are often in table format)
        for table in doc.tables:
            table_rows = []
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    table_rows.append(row_text)
            if table_rows:
                paragraphs.append("\n[TABLE]\n" + "\n".join(table_rows) + "\n[/TABLE]")
        return "\n\n".join(paragraphs)
    except ImportError:
        raise RuntimeError("python-docx not installed. Run: pip install python-docx")


# ── Text Cleaning ──────────────────────────────────────────────────────────────

def clean_extracted_text(raw_text: str) -> str:
    """
    Clean raw extracted text for AI consumption.

    Removes:
    - Excessive whitespace / blank lines
    - Page numbers standing alone (e.g. "12", "Page 3 of 8")
    - Repetitive headers/footers (e.g. "SUZUKI" repeated every page)
    - Non-printable characters
    """
    if not raw_text:
        return ""

    # Remove page markers we inserted
    text = re.sub(r'\[Page \d+\]\n', '', raw_text)

    # Collapse 3+ blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove standalone page numbers
    text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE)

    # Remove "Page X of Y" patterns
    text = re.sub(r'Page\s+\d+\s+of\s+\d+', '', text, flags=re.IGNORECASE)

    # Collapse multiple spaces
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # Strip non-printable chars except newline and tab
    text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]', '', text)

    return text.strip()


# ── Section Classification ─────────────────────────────────────────────────────

def classify_section(text: str) -> str:
    """
    Detect what section type a chunk belongs to based on keywords.
    Returns the best-matching section type or 'general'.
    """
    text_lower = text.lower()
    scores = {}
    for section, keywords in SECTION_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[section] = score
    if not scores:
        return "general"
    return max(scores, key=lambda k: scores[k])


# ── Chunking ───────────────────────────────────────────────────────────────────

def split_into_chunks(text: str) -> List[Tuple[int, str]]:
    """
    Split text into overlapping chunks of ~CHUNK_SIZE characters.
    
    Strategy:
    1. First try to split on section headings (## markers from DOCX)
    2. Then split on double newlines (paragraph breaks)
    3. Finally fall back to fixed-size character chunks with overlap

    Returns list of (index, chunk_text) tuples.
    """
    chunks = []

    # Try heading-based splitting first
    if "## " in text:
        sections = re.split(r'\n## ', text)
        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue
            # If section is small enough, keep as one chunk
            if len(section) <= CHUNK_SIZE * 1.5:
                chunks.append(section)
            else:
                # Sub-split by paragraphs
                chunks.extend(_split_by_paragraphs(section))
    else:
        chunks = _split_by_paragraphs(text)

    # Clean and return with index
    result = []
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if len(chunk) >= 50:  # ignore tiny fragments
            result.append((i, chunk))
    return result


def _split_by_paragraphs(text: str) -> List[str]:
    """Split text on double newlines, merging short paragraphs."""
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < CHUNK_SIZE:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # If single paragraph is larger than chunk size, split by sentence
            if len(para) > CHUNK_SIZE:
                sub_chunks = _split_by_sentences(para)
                chunks.extend(sub_chunks[:-1])
                current = sub_chunks[-1] if sub_chunks else ""
            else:
                current = para

    if current:
        chunks.append(current)
    return chunks


def _split_by_sentences(text: str) -> List[str]:
    """Last resort: split oversized paragraphs by sentence."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) < CHUNK_SIZE:
            current = (current + " " + sentence).strip()
        else:
            if current:
                chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


# ── Main Processing Function ───────────────────────────────────────────────────

def process_document(document_id: str, db: Session) -> dict:
    """
    Full processing pipeline for an uploaded document.
    
    Called after upload completes. In production this would run
    as a background task (FastAPI BackgroundTasks or Celery).

    Returns summary dict with chunk_count and status.
    """
    doc = db.query(Document).filter(Document.document_id == document_id).first()
    if not doc:
        return {"error": "Document not found"}

    # Mark as processing
    doc.processing_status = "processing"  # type: ignore[assignment]
    doc.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    try:
        # ── Step 1: Extract raw text ──────────────────────────────────────────
        if doc.file_type == "pdf":  # type: ignore[comparison-overlap]
            raw_text = extract_text_from_pdf(str(doc.file_path))
        elif doc.file_type == "docx":  # type: ignore[comparison-overlap]
            raw_text = extract_text_from_docx(str(doc.file_path))
        else:
            # Image — OCR would go here (Tesseract). For now, return placeholder.
            raw_text = f"[Image document: {doc.filename} — OCR processing not yet implemented]"

        # ── Step 2: Clean text ────────────────────────────────────────────────
        clean_text = clean_extracted_text(raw_text)

        if not clean_text:
            raise ValueError("No readable text could be extracted from this document")

        # Store full cleaned text on the document
        doc.extracted_text = clean_text  # type: ignore[assignment]

        # ── Step 3: Split into chunks ─────────────────────────────────────────
        chunk_tuples = split_into_chunks(clean_text)

        if not chunk_tuples:
            raise ValueError("Document text could not be split into chunks")

        # ── Step 4: Delete any old chunks (reprocessing case) ─────────────────
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()

        # ── Step 5: Save chunks ───────────────────────────────────────────────
        for idx, chunk_text in chunk_tuples:
            chunk = DocumentChunk(
                chunk_id=uuid.uuid4(),
                document_id=doc.document_id,
                dealership_id=doc.dealership_id,
                car_model_id=doc.car_model_id,
                chunk_index=idx,
                chunk_text=chunk_text,
                section_type=classify_section(chunk_text),
                char_count=len(chunk_text),
            )
            db.add(chunk)

        # ── Step 6: Update document record ────────────────────────────────────
        doc.processing_status = "completed"  # type: ignore[assignment]
        doc.chunk_count = len(chunk_tuples)  # type: ignore[assignment]
        doc.updated_at = datetime.utcnow()  # type: ignore[assignment]
        db.commit()

        return {
            "document_id": str(document_id),
            "processing_status": "completed",
            "chunk_count": len(chunk_tuples),
            "message": f"Successfully extracted {len(chunk_tuples)} chunks from '{doc.filename}'"
        }

    except Exception as e:
        db.rollback()
        doc.processing_status = "failed"  # type: ignore[assignment]
        doc.processing_error = str(e)  # type: ignore[assignment]
        doc.updated_at = datetime.utcnow()  # type: ignore[assignment]
        db.commit()
        return {
            "document_id": str(document_id),
            "processing_status": "failed",
            "chunk_count": 0,
            "message": f"Processing failed: {str(e)}"
        }