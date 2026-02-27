from fastapi import APIRouter, Depends
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.run_history import RunHistory
from app.schemas.run import RunHistoryOut

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunHistoryOut])
def list_runs(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return db.query(RunHistory).order_by(desc(RunHistory.started_at)).limit(100).all()
