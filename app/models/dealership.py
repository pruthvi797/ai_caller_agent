import uuid
from sqlalchemy import Column, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Dealership(Base):
    __tablename__ = "dealerships"

    dealership_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String)
    location = Column(String)
    showroom_address = Column(String)
    contact_phone = Column(String)
    logo = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)