from datetime import datetime

from pydantic import BaseModel


class SourceConfigIn(BaseModel):
    source_name: str
    config: dict = {}
    status: str = "connected"
    notes: str | None = None


class SourceConfigOut(BaseModel):
    id: int
    source_name: str
    config: dict
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
