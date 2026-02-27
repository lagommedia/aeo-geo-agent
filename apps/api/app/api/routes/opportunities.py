from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.opportunity import QueryOpportunity
from app.schemas.opportunity import OpportunityOut, OpportunityStatusUpdate

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


@router.get("", response_model=list[OpportunityOut])
def list_opportunities(
    source: str | None = Query(default=None),
    funnel_stage: str | None = Query(default=None),
    intent: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(QueryOpportunity)
    if source:
        q = q.filter(QueryOpportunity.source == source)
    if funnel_stage:
        q = q.filter(QueryOpportunity.funnel_stage == funnel_stage)
    if intent:
        q = q.filter(QueryOpportunity.intent == intent)
    if status:
        q = q.filter(QueryOpportunity.status == status)
    return q.order_by(desc(QueryOpportunity.priority_score)).all()


@router.get("/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    return opp


@router.patch("/{opportunity_id}", response_model=OpportunityOut)
def update_status(opportunity_id: int, payload: OpportunityStatusUpdate, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    opp.status = payload.status
    db.commit()
    db.refresh(opp)
    return opp


@router.get("/{opportunity_id}/brief")
def export_brief(opportunity_id: int, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    opp = db.query(QueryOpportunity).filter(QueryOpportunity.id == opportunity_id).one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": opportunity_id, "brief": opp.brief}
