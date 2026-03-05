import os
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Query
from sqlalchemy.orm import Session

from app.models.document_model import Document
from app.models.document_chunk_model import DocumentChunk
from app.models.user import User
from app.schemas.document_schema import (
    DocumentResponse, DocumentDetailResponse, ChunkResponse, ProcessingResult
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.document_processor import process_document

router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = "uploads/documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
}
MAX_FILE_SIZE_MB = 20


def _require_dealership(current_user: User):
    if not current_user.dealership_id:  # type: ignore[truthy-function]
        raise HTTPException(
            status_code=400,
            detail="You must create a dealership first (POST /dealership/create)"
        )


def _get_doc_or_404(document_id: str, dealership_id, db: Session) -> Document:
    doc = db.query(Document).filter(
        Document.document_id == document_id,
        Document.dealership_id == dealership_id,
        Document.deleted_at.is_(None)
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(default="brochure"),
    title: Optional[str] = Form(default=None),
    description: Optional[str] = Form(default=None),
    car_model_id: Optional[str] = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a car brochure, pricing sheet, or promotional document.
    Accepted: PDF, DOCX, JPG, PNG, WEBP (max 20MB).
    Text extraction runs automatically in the background.
    """
    _require_dealership(current_user)

    content_type = file.content_type or ""
    file_type = ALLOWED_TYPES.get(content_type)
    if not file_type:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{content_type}'. Allowed: PDF, DOCX, JPG, PNG, WEBP"
        )

    valid_doc_types = {
        "brochure", "pricing_sheet", "feature_comparison",
        "promotional_offer", "spec_sheet", "other"
    }
    if document_type not in valid_doc_types:
        raise HTTPException(
            status_code=422,
            detail=f"document_type must be one of: {', '.join(sorted(valid_doc_types))}"
        )

    file_bytes = await file.read()
    file_size = len(file_bytes)
    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large. Max {MAX_FILE_SIZE_MB}MB")
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    original_name = file.filename or "document"
    ext = os.path.splitext(original_name)[1].lower() or f".{file_type}"
    stored_name = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_name)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    now = datetime.utcnow()
    doc = Document(
        document_id=uuid.uuid4(),
        dealership_id=current_user.dealership_id,
        car_model_id=car_model_id if car_model_id else None,
        uploaded_by=current_user.user_id,
        filename=original_name,
        stored_filename=stored_name,
        file_path=file_path,
        file_type=file_type,
        mime_type=content_type,
        file_size_bytes=file_size,
        document_type=document_type,
        processing_status="pending",
        chunk_count=0,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_document, str(doc.document_id), db)
    return doc


@router.get("/", response_model=List[DocumentResponse])
def list_documents(
    document_type: Optional[str] = Query(None),
    processing_status: Optional[str] = Query(None),
    car_model_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all uploaded documents for your dealership."""
    _require_dealership(current_user)

    query = db.query(Document).filter(
        Document.dealership_id == current_user.dealership_id,
        Document.deleted_at.is_(None)
    )
    if document_type:
        query = query.filter(Document.document_type == document_type)
    if processing_status:
        query = query.filter(Document.processing_status == processing_status)
    if car_model_id:
        query = query.filter(Document.car_model_id == car_model_id)

    return query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full document details including extracted text."""
    _require_dealership(current_user)
    return _get_doc_or_404(document_id, current_user.dealership_id, db)


@router.get("/{document_id}/chunks", response_model=List[ChunkResponse])
def get_document_chunks(
    document_id: str,
    section_type: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all extracted chunks for a document, optionally filtered by section_type."""
    _require_dealership(current_user)
    doc = _get_doc_or_404(document_id, current_user.dealership_id, db)

    if doc.processing_status != "completed":  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=400,
            detail=f"Document not yet processed (status: {doc.processing_status})"
        )

    query = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    )
    if section_type:
        query = query.filter(DocumentChunk.section_type == section_type)

    return query.order_by(DocumentChunk.chunk_index).all()


@router.post("/{document_id}/reprocess", response_model=ProcessingResult)
def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Re-trigger text extraction. Useful when initial processing failed."""
    _require_dealership(current_user)
    doc = _get_doc_or_404(document_id, current_user.dealership_id, db)

    doc.processing_status = "pending"       # type: ignore[assignment]
    doc.processing_error = None             # type: ignore[assignment]
    doc.updated_at = datetime.utcnow()      # type: ignore[assignment]
    db.commit()

    background_tasks.add_task(process_document, str(doc.document_id), db)

    return ProcessingResult(
        document_id=doc.document_id,  # type: ignore[arg-type]
        processing_status="pending",
        chunk_count=doc.chunk_count or 0,  # type: ignore[arg-type]
        message="Reprocessing started. Check status via GET /documents/{id}"
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft-delete a document. File and chunks are preserved."""
    _require_dealership(current_user)
    doc = _get_doc_or_404(document_id, current_user.dealership_id, db)

    doc.deleted_at = datetime.utcnow()      # type: ignore[assignment]
    doc.is_active = False                   # type: ignore[assignment]
    doc.updated_at = datetime.utcnow()      # type: ignore[assignment]
    db.commit()

    return {"message": f"Document '{doc.filename}' has been deleted"}