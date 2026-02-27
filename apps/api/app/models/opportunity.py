from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from app.models.base import Base


JSONType = JSONB().with_variant(JSON, "sqlite")


class QueryOpportunity(Base):
    __tablename__ = "query_opportunities"

    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(String(500), nullable=False, index=True)
    source = Column(String(100), nullable=False)
    intent = Column(String(50), nullable=False)
    funnel_stage = Column(String(20), nullable=False)
    trend_score = Column(Float, nullable=False, default=0)
    trend_reason = Column(Text, nullable=False, default="")
    refresh_needed = Column(Boolean, nullable=False, default=False)
    refresh_reason = Column(Text, nullable=True)
    ai_snippet_reco = Column(JSONType, nullable=False, default=dict)
    brief = Column(Text, nullable=False, default="")
    priority_score = Column(Float, nullable=False, default=0)
    priority_explanation = Column(Text, nullable=False, default="")
    recommended_actions = Column(JSONType, nullable=False, default=list)
    links = Column(JSONType, nullable=False, default=list)
    status = Column(String(30), nullable=False, default="new")
    metadata_json = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
