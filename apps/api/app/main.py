from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import agents, auth, metrics, opportunities, runs, sources
from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models import Base
from app.models.user import User

configure_logging()
app = FastAPI(title="AI Content Demand Capture Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(agents.router)
app.include_router(opportunities.router)
app.include_router(runs.router)
app.include_router(sources.router)
app.include_router(metrics.router)


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)

    # Keep auth bootstrap only. Do not auto-run strategist ingestion.
    db = SessionLocal()
    try:
        demo_user = db.query(User).filter(User.email == settings.demo_email).one_or_none()
        if not demo_user:
            db.add(User(email=settings.demo_email, password_hash=hash_password(settings.demo_password)))
            db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
