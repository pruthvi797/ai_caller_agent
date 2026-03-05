import uuid
from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class DocumentType(str, Enum):
    brochure           = "brochure"
    pricing_sheet      = "pricing_sheet"
    feature_comparison = "feature_comparison"
    promotional_offer  = "promotional_offer"
    spec_sheet         = "spec_sheet"
    other              = "other"

class ProcessingStatus(str, Enum):
    pending    = "pending"
    processing = "processing"
    processed  = "processed"
    failed     = "failed"

ALLOWED_MIME_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "text/plain": "txt",
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
}

MAX_FILE_SIZE_MB = 20


# ── Document Response ─────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    document_id: uuid.UUID
    dealership_id: uuid.UUID
    car_model_id: Optional[uuid.UUID]
    filename: str
    file_type: str
    mime_type: Optional[str]
    file_size_bytes: Optional[int]
    document_type: str
    processing_status: str
    processed_at: Optional[datetime]
    chunk_count: Optional[int]
    is_active: bool
    uploaded_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentDetailResponse(DocumentResponse):
    """Extended response that includes extracted text - for internal/admin use"""
    extracted_text: Optional[str]
    file_path: str


# ── Document Update ───────────────────────────────────────────────────────────

class DocumentUpdate(BaseModel):
    """Only metadata fields can be updated after upload. File cannot be changed."""
    document_type: Optional[DocumentType] = None
    car_model_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.document_type is None and self.car_model_id is None:
            raise ValueError("No fields provided to update")
        return self


# ── Chunk Schemas ─────────────────────────────────────────────────────────────

class ChunkResponse(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    chunk_text: str
    section_type: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Knowledge Base Schemas ────────────────────────────────────────────────────

class KnowledgeBaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    document_ids: List[uuid.UUID]

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError("Knowledge base name cannot be blank")
        return v.strip()

    @field_validator("document_ids")
    @classmethod
    def must_have_documents(cls, v):
        if not v:
            raise ValueError("At least one document must be added to the knowledge base")
        return v


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.name is None and self.description is None:
            raise ValueError("No fields provided to update")
        return self

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        if v is not None and not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip() if v else v


class KnowledgeBaseResponse(BaseModel):
    kb_id: uuid.UUID
    dealership_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    description: Optional[str]
    status: str
    build_error: Optional[str]
    built_at: Optional[datetime]
    total_documents: int
    total_chunks: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class KnowledgeBaseWithDocuments(KnowledgeBaseResponse):
    """Full KB with embedded document list"""
    documents: List[DocumentResponse] = []


# ── Knowledge Base Document Management ───────────────────────────────────────

class KBAddDocuments(BaseModel):
    document_ids: List[uuid.UUID]

    @field_validator("document_ids")
    @classmethod
    def must_not_be_empty(cls, v):
        if not v:
            raise ValueError("document_ids list cannot be empty")
        return v


class KBRemoveDocument(BaseModel):
    document_id: uuid.UUID


# ── Semantic Search ───────────────────────────────────────────────────────────

class KBSearchRequest(BaseModel):
    query: str
    top_k: int = 5

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError("Search query cannot be blank")
        return v.strip()

    @field_validator("top_k")
    @classmethod
    def valid_top_k(cls, v):
        if v < 1 or v > 20:
            raise ValueError("top_k must be between 1 and 20")
        return v


class KBSearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    chunk_text: str
    section_type: Optional[str]
    similarity_score: float


# ── Processing Result ─────────────────────────────────────────────────────────

class ProcessingResult(BaseModel):
    document_id: uuid.UUID
    processing_status: str
    chunk_count: int
    message: str