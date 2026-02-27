from datetime import datetime

from pydantic import BaseModel


class RunHistoryOut(BaseModel):
    id: int
    run_type: str
    status: str
    details: dict
    error: str | None
    started_at: datetime
    finished_at: datetime | None

    class Config:
        from_attributes = True
