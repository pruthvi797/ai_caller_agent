import uuid
from sqlalchemy import Column, String, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class AgentConfig(Base):
    __tablename__ = "agent_config"

    agent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"))

    voice = Column(String)
    system_prompt = Column(String)
    knowledge_base_id = Column(String)

    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)