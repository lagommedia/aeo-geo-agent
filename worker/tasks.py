from datetime import datetime, timezone

from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.models.run_history import RunHistory
from app.services.ingestion import run_ingestion

from celery_app import celery_app

logger = get_task_logger(__name__)


def _record(run_type: str, status: str, details: dict | None = None, error: str | None = None):
    db = SessionLocal()
    try:
        row = RunHistory(
            run_type=run_type,
            status=status,
            details=details or {},
            error=error,
            finished_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


@celery_app.task(name="tasks.run_nightly_ingestion")
def run_nightly_ingestion():
    logger.info("Running nightly ingestion")
    db = SessionLocal()
    try:
        result = run_ingestion(db)
        _record("nightly_ingestion_task", "success", result)
        return result
    except Exception as exc:  # pragma: no cover
        _record("nightly_ingestion_task", "failed", error=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="tasks.run_hourly_trend_detection")
def run_hourly_trend_detection():
    _record("hourly_trend_detection", "success", {"message": "Trend detection runs inside ingestion for MVP"})
    return {"ok": True}


@celery_app.task(name="tasks.run_weekly_competitor_velocity")
def run_weekly_competitor_velocity():
    _record("weekly_competitor_velocity", "success", {"message": "Velocity recomputed during ingestion for MVP"})
    return {"ok": True}
