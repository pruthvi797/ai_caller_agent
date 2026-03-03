import uuid
from sqlalchemy import Column, String, Date, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    dealership_id = Column(UUID(as_uuid=True), ForeignKey("dealerships.dealership_id"))
    car_model_id = Column(UUID(as_uuid=True), ForeignKey("car_models.car_model_id"))

    campaign_name = Column(String)
    promotion_type = Column(String)

    start_date = Column(Date)
    end_date = Column(Date)

    status = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)