from celery import Celery

from apps.api.config import get_settings

settings = get_settings()

celery_app = Celery(
    "raindeer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.broker_connection_retry_on_startup = True


@celery_app.task(name="worker.ping")
def ping() -> str:
    return "pong"
