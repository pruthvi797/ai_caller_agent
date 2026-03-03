import uuid
from sqlalchemy import Column, String, DECIMAL, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class CarModel(Base):
    __tablename__ = "car_models"

    car_model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    dealership_id = Column(UUID(as_uuid=True), ForeignKey("dealerships.dealership_id"))

    model_name = Column(String)
    variant = Column(String)

    price_min = Column(DECIMAL)
    price_max = Column(DECIMAL)

    fuel_type = Column(String)
    category = Column(String)

    features = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)