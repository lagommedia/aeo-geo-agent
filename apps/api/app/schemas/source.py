from datetime import datetime

from pydantic import BaseModel


class SourceConfigIn(BaseModel):
    source_name: str
    config: dict = {}
    status: str = "connected"
    notes: str | None = None


class SourceCredentialIn(BaseModel):
    source_name: str
    credentials: dict
    notes: str | None = None


class OAuthStartResponse(BaseModel):
    source_name: str
    auth_url: str
    state: str


class OAuthCallbackIn(BaseModel):
    code: str
    state: str


class SourceTestResponse(BaseModel):
    source_name: str
    status: str
    message: str
    details: dict = {}


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
