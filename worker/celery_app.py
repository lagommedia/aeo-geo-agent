from celery import Celery

from app.core.config import settings

celery_app = Celery("demand_capture", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.beat_schedule = {
    "nightly-ingestion": {
        "task": "tasks.run_nightly_ingestion",
        "schedule": 60.0,
    },
    "hourly-trends": {
        "task": "tasks.run_hourly_trend_detection",
        "schedule": 60.0,
    },
    "weekly-competitor-velocity": {
        "task": "tasks.run_weekly_competitor_velocity",
        "schedule": 300.0,
    },
}

celery_app.conf.timezone = "UTC"
