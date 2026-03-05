from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import datetime
from uuid import UUID


KB_STATUSES = {"draft", "compiling", "ready", "failed"}


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None

    # List of document IDs to include in this KB
    document_ids: Optional[List[UUID]] = []

    # Optionally restrict to specific car models
    car_model_ids: Optional[List[UUID]] = []

    @validator("name")
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("name is required")
        return v.strip()


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None and not v.strip():
            raise ValueError("name cannot be blank")
        return v.strip() if v else v


class KnowledgeBaseResponse(BaseModel):
    kb_id: UUID
    dealership_id: UUID
    name: str
    description: Optional[str]
    status: str
    total_chunks: Optional[int]
    word_count: Optional[int]
    source_document_ids: Optional[str]   # raw JSON string
    car_model_ids: Optional[str]
    elevenlabs_kb_id: Optional[str]
    last_synced_at: Optional[datetime]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseDetailResponse(KnowledgeBaseResponse):
    """Includes compiled content — only returned on GET /kb/{id}."""
    compiled_content: Optional[str]


class KBCompileRequest(BaseModel):
    """
    Request body for POST /kb/{id}/compile.
    Optionally override which documents to include.
    """
    document_ids: Optional[List[UUID]] = None   # if None, use all active docs for dealership
    car_model_ids: Optional[List[UUID]] = None  # if None, include all car models
    include_section_types: Optional[List[str]] = None  # e.g. ["pricing", "features"]