import uuid
from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Call(Base):
    __tablename__ = "calls"

    call_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.lead_id"))
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"))

    call_status = Column(String)
    call_duration = Column(Integer)
    call_outcome = Column(String)

    transcript = Column(String)
    call_recording_url = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)