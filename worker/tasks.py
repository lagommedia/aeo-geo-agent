from datetime import datetime, timezone

from celery.utils.log import get_task_logger

from app.core.database import SessionLocal
from app.models.run_history import RunHistory

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
    msg = "disabled: use manual evaluate + board pull workflow"
    logger.info(msg)
    _record("nightly_ingestion_task", "success", {"message": msg})
    return {"ok": True, "message": msg}


@celery_app.task(name="tasks.run_hourly_trend_detection")
def run_hourly_trend_detection():
    _record("hourly_trend_detection", "success", {"message": "disabled"})
    return {"ok": True, "message": "disabled"}


@celery_app.task(name="tasks.run_weekly_competitor_velocity")
def run_weekly_competitor_velocity():
    _record("weekly_competitor_velocity", "success", {"message": "disabled"})
    return {"ok": True, "message": "disabled"}


@celery_app.task(name="tasks.run_weekly_strategist_orchestration")
def run_weekly_strategist_orchestration():
    msg = "disabled: use manual evaluate + board pull workflow"
    logger.info(msg)
    _record("weekly_strategist_orchestration", "success", {"message": msg})
    return {"ok": True, "message": msg}
