from celery import Celery

from app.core.config import settings

celery_app = Celery("demand_capture", broker=settings.redis_url, backend=settings.redis_url)

# Auto strategist ingestion is intentionally disabled.
# Opportunity creation now happens via manual evaluate + board pull workflow.
celery_app.conf.beat_schedule = {}
celery_app.conf.timezone = "UTC"
