import json
import uuid
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.models.knowledge_base_model import KnowledgeBase
from app.models.user import User
from app.schemas.knowledge_base_schema import (
    KnowledgeBaseCreate, KnowledgeBaseUpdate,
    KnowledgeBaseResponse, KnowledgeBaseDetailResponse,
    KBCompileRequest
)
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.knowledge_base_service import compile_knowledge_base

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


def _require_dealership(current_user: User):
    if not current_user.dealership_id:  # type: ignore[truthy-function]
        raise HTTPException(
            status_code=400,
            detail="You must create a dealership first (POST /dealership/create)"
        )


def _get_kb_or_404(kb_id: str, dealership_id, db: Session) -> KnowledgeBase:
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.kb_id == kb_id,
        KnowledgeBase.dealership_id == dealership_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.post("/", response_model=KnowledgeBaseResponse, status_code=201)
def create_knowledge_base(
    body: KnowledgeBaseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new knowledge base. Then call POST /kb/{id}/compile to populate it."""
    _require_dealership(current_user)

    now = datetime.utcnow()
    kb = KnowledgeBase(
        kb_id=uuid.uuid4(),
        dealership_id=current_user.dealership_id,
        name=body.name.strip(),
        description=body.description,
        status="draft",
        total_chunks=0,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return kb


@router.get("/", response_model=List[KnowledgeBaseResponse])
def list_knowledge_bases(
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all knowledge bases for your dealership."""
    _require_dealership(current_user)

    query = db.query(KnowledgeBase).filter(
        KnowledgeBase.dealership_id == current_user.dealership_id,
        KnowledgeBase.is_active == True
    )
    if status:
        query = query.filter(KnowledgeBase.status == status)

    return query.order_by(KnowledgeBase.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{kb_id}", response_model=KnowledgeBaseDetailResponse)
def get_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full KB including compiled_content — the text fed to the AI agent."""
    _require_dealership(current_user)
    return _get_kb_or_404(kb_id, current_user.dealership_id, db)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(
    kb_id: str,
    body: KnowledgeBaseUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update KB name or description."""
    _require_dealership(current_user)
    kb = _get_kb_or_404(kb_id, current_user.dealership_id, db)

    update_data = body.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    for field, value in update_data.items():
        setattr(kb, field, value)
    kb.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()
    db.refresh(kb)
    return kb


@router.post("/{kb_id}/compile")
def compile_kb(
    kb_id: str,
    body: KBCompileRequest = KBCompileRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compile the KB from all processed document chunks for your dealership.
    After this, GET /kb/{id} will return structured compiled_content ready
    for the ElevenLabs AI agent.
    """
    _require_dealership(current_user)
    kb = _get_kb_or_404(kb_id, current_user.dealership_id, db)

    if kb.status == "compiling":  # type: ignore[comparison-overlap]
        raise HTTPException(status_code=400, detail="Already compiling. Please wait.")

    document_ids = [str(d) for d in body.document_ids] if body.document_ids else None
    car_model_ids = [str(c) for c in body.car_model_ids] if body.car_model_ids else None

    result = compile_knowledge_base(
        kb_id=str(kb_id),
        db=db,
        document_ids=document_ids,
        car_model_ids=car_model_ids,
        include_section_types=body.include_section_types
    )

    if result.get("status") == "failed":
        raise HTTPException(status_code=422, detail=result.get("message"))

    return result


@router.get("/{kb_id}/preview")
def preview_kb_content(
    kb_id: str,
    max_chars: int = Query(2000, ge=100, le=10000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Preview first N characters of compiled KB. Check it looks right before linking to campaign."""
    _require_dealership(current_user)
    kb = _get_kb_or_404(kb_id, current_user.dealership_id, db)

    if kb.status != "ready":  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=400,
            detail=f"KB not ready (status: {kb.status}). Run POST /kb/{kb_id}/compile first."
        )

    content = str(kb.compiled_content) if kb.compiled_content is not None else ""
    preview = content[:max_chars]
    truncated = len(content) > max_chars

    return {
        "kb_id": str(kb.kb_id),
        "name": kb.name,
        "status": kb.status,
        "total_chars": len(content),
        "word_count": kb.word_count,
        "preview": preview,
        "truncated": truncated,
    }


@router.delete("/{kb_id}")
def delete_knowledge_base(
    kb_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Deactivate a KB. Compiled content is preserved for any linked campaigns."""
    _require_dealership(current_user)
    kb = _get_kb_or_404(kb_id, current_user.dealership_id, db)

    kb.is_active = False  # type: ignore[assignment]
    kb.updated_at = datetime.utcnow()  # type: ignore[assignment]
    db.commit()

    return {"message": f"Knowledge base '{kb.name}' has been deactivated"}