from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Field, SQLModel, Session, create_engine, select

from content_demand_agent.config import settings


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str | None = None
    google_sub: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PlatformConnection(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    platform: str = Field(index=True)
    login_method: str
    username: str | None = None
    credential_ref: str | None = None
    google_verified: bool = False
    google_email: str | None = None
    status: str = "connected"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    db_file = settings.database_url.replace("sqlite:///", "")
    if db_file:
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == email)).first()


def get_user_by_google_sub(session: Session, sub: str) -> User | None:
    return session.exec(select(User).where(User.google_sub == sub)).first()
