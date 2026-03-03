import uuid
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Lead(Base):
    __tablename__ = "leads"

    lead_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"))

    name = Column(String)
    phone = Column(String)
    email = Column(String)

    budget = Column(DECIMAL)
    current_car = Column(String)
    interest_level = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)