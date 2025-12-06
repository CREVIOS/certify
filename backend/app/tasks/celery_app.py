"""Celery application configuration."""

from celery import Celery
from celery.signals import worker_ready, worker_shutdown
from loguru import logger

from app.core.config import settings

# Create Celery app
celery_app = Celery(
    "ipo_verification",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        'app.tasks.document_tasks',
        'app.tasks.verification_tasks'
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=settings.CELERY_TASK_TRACK_STARTED,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,  # Results expire after 1 hour
)


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Execute when worker is ready."""
    logger.info("Celery worker is ready")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Execute when worker is shutting down."""
    logger.info("Celery worker is shutting down")
