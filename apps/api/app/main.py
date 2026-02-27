from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, metrics, opportunities, runs, sources
from app.core.database import engine
from app.core.logging import configure_logging
from app.models import Base
from app.services.ingestion import run_ingestion
from app.core.database import SessionLocal

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
app.include_router(opportunities.router)
app.include_router(runs.router)
app.include_router(sources.router)
app.include_router(metrics.router)


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/admin/run-ingestion")
def admin_run_ingestion():
    db = SessionLocal()
    try:
        result = run_ingestion(db)
        return {"status": "ok", "result": result}
    finally:
        db.close()
