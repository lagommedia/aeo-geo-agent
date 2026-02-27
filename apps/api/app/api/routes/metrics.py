from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.schemas.metrics import MetricsOut
from app.services.metrics import compute_ai_citation_share, compute_competitor_velocity, compute_non_branded_pipeline

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", response_model=MetricsOut)
def get_metrics(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return MetricsOut(
        ai_citation_share=compute_ai_citation_share(db),
        non_branded_pipeline=compute_non_branded_pipeline(db),
        competitor_velocity=compute_competitor_velocity(db),
    )
