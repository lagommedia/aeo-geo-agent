from datetime import datetime

from pydantic import BaseModel


class OpportunityBase(BaseModel):
    query_text: str
    source: str
    intent: str
    funnel_stage: str
    trend_score: float
    trend_reason: str
    refresh_needed: bool
    refresh_reason: str | None = None
    ai_snippet_reco: dict
    brief: str
    priority_score: float
    priority_explanation: str
    recommended_actions: list[str]
    links: list[str]
    status: str
    metadata_json: dict


class OpportunityOut(OpportunityBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OpportunityStatusUpdate(BaseModel):
    status: str
