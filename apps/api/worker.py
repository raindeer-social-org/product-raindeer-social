from celery import Celery

from apps.api.config import get_settings
from apps.api.config.database import SessionLocal
from packages.agents.pipeline.trigger import trigger_due_pipelines

settings = get_settings()

celery_app = Celery(
    "raindeer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.broker_connection_retry_on_startup = True

# Issue #29: on a recurring schedule, poll ContentCalendarEvent for events
# approaching their target_datetime and start the #18 pipeline for each.
# Runs every minute — frequent enough that Settings.pipeline_trigger_lead_
# minutes (the configurable lead-time window) is honored to within about a
# minute, without needing sub-minute precision anywhere else in the
# system. The actual selection/claim/pipeline-start logic lives in
# packages/agents/pipeline/trigger.py, not here, so it's unit-testable
# without any Celery machinery.
celery_app.conf.beat_schedule = {
    "trigger-due-pipelines": {
        "task": "worker.trigger_due_pipelines",
        "schedule": 60.0,
    },
}


@celery_app.task(name="worker.ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="worker.trigger_due_pipelines")
def trigger_due_pipelines_task() -> int:
    """Celery Beat entrypoint for Issue #29's pipeline trigger.

    A thin wrapper: opens its own DB session (Celery tasks aren't FastAPI
    request handlers, so there's no `Depends(get_db)` to lean on),
    delegates all real work to trigger_due_pipelines, and commits on
    success / rolls back on failure. Returns the number of pipeline runs
    started or advanced this poll, mostly useful for task-result
    inspection/logging.
    """
    settings = get_settings()
    db = SessionLocal()
    try:
        started = trigger_due_pipelines(
            db,
            lead_time_minutes=settings.pipeline_trigger_lead_minutes,
        )
        db.commit()
        return len(started)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
