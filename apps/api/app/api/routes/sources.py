from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.source_config import SourceConfig
from app.schemas.source import SourceConfigIn, SourceConfigOut

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceConfigOut])
def list_sources(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return db.query(SourceConfig).all()


@router.post("", response_model=SourceConfigOut)
def upsert_source(payload: SourceConfigIn, db: Session = Depends(get_db), _user=Depends(get_current_user)):
    row = db.query(SourceConfig).filter(SourceConfig.source_name == payload.source_name).one_or_none()
    if row:
        row.config = payload.config
        row.status = payload.status
        row.notes = payload.notes
    else:
        row = SourceConfig(**payload.model_dump())
        db.add(row)
    db.commit()
    db.refresh(row)
    return row
