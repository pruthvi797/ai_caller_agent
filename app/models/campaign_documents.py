from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class CampaignDocument(Base):
    __tablename__ = "campaign_documents"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"), primary_key=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.document_id"), primary_key=True)