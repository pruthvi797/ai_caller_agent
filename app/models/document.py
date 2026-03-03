import uuid
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Document(Base):
    __tablename__ = "documents"

    document_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    car_model_id = Column(UUID(as_uuid=True), ForeignKey("car_models.car_model_id"))

    file_name = Column(String)
    file_type = Column(String)
    file_path = Column(String)

    processed_text = Column(String)

    uploaded_at = Column(TIMESTAMP)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)