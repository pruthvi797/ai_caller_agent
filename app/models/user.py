import uuid
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    email = Column(String, unique=True)
    password_hash = Column(String)
    phone = Column(String)

    dealership_id = Column(UUID(as_uuid=True), ForeignKey("dealerships.dealership_id"))

    role = Column(String)
    permissions = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)