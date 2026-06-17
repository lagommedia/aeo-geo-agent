from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.opportunity import QueryOpportunity
from app.services.aeo_geo_agents import AGENT_PROMPTS, run_agent

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRunIn(BaseModel):
    prompt: str
    opportunity_id: int | None = None
    context: dict | None = None


class AgentRunOut(BaseModel):
    agent: str
    output: str
    provider: str
    model: str | None = None


@router.get("", response_model=list[str])
def list_agents(_user=Depends(get_current_user)):
    return sorted(AGENT_PROMPTS.keys())


@router.post("/{agent_name}/run", response_model=AgentRunOut)
def run_named_agent(
    agent_name: str,
    payload: AgentRunIn,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    ctx = dict(payload.context or {})
    if payload.opportunity_id is not None:
        opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == payload.opportunity_id).one_or_none()
        if not opp:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        ctx["opportunity"] = {
            "id": opp.id,
            "query_text": opp.query_text,
            "source": opp.source,
            "intent": opp.intent,
            "funnel_stage": opp.funnel_stage,
            "trend_score": opp.trend_score,
            "priority_score": opp.priority_score,
            "status": opp.status,
            "metadata_json": opp.metadata_json or {},
            "links": opp.links or [],
        }

    try:
        result = run_agent(db, agent_name, payload.prompt, ctx)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AgentRunOut(**result)
