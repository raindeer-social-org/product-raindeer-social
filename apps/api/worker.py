import logging
import uuid

from celery import Celery, Task

from apps.api.config import get_settings
from apps.api.config.database import SessionLocal
from apps.api.models import Post
from apps.api.services import notifications, publish_queue

settings = get_settings()

celery_app = Celery(
    "raindeer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.broker_connection_retry_on_startup = True

logger = logging.getLogger(__name__)

# Issue #31's acceptance criteria: transient failures retry with
# exponential backoff, "capped at a defined max attempts". These are that
# cap and Celery's own backoff knobs (retry_backoff=True below) — the Nth
# retry waits roughly min(PUBLISH_RETRY_BACKOFF_BASE * 2**N,
# PUBLISH_RETRY_BACKOFF_MAX) seconds, with jitter so a burst of failures
# across many posts doesn't all retry in lockstep.
PUBLISH_MAX_RETRIES = 5
PUBLISH_RETRY_BACKOFF_BASE = 30
PUBLISH_RETRY_BACKOFF_MAX = 600


@celery_app.task(name="worker.ping")
def ping() -> str:
    return "pong"


class _PublishTask(Task):
    """Celery calls Task.on_failure exactly once per task invocation
    chain — after the *final* failed attempt, whether that's because
    publish_post_task raised something autoretry_for doesn't retry, or
    because retry_backoff's retries were exhausted. That's precisely the
    "marks status=failed only after retries are exhausted" moment Issue
    #31 asks for: publish_queue.publish_post already recorded every
    individual attempt's per-platform result/error as it happened (so
    nothing is silently dropped mid-retry — see that module's docstring),
    and this is where the terminal failed state gets set, using whatever
    error the last attempt raised."""

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        post_id = args[0] if args else kwargs.get("post_id")
        if post_id is None:
            logger.error("Publish task %s failed with no post_id in args/kwargs", task_id)
            return

        db = SessionLocal()
        try:
            publish_queue.mark_post_failed(db, uuid.UUID(post_id), reason=str(exc))
            db.commit()

            # Issue #32 — fire the publish-failure notification within
            # this same job run, right after the terminal FAILED state is
            # committed. notify_publish_failure never raises (see
            # apps/api/services/notifications.py's module docstring), so
            # this can't turn a successfully-recorded failure into an
            # unhandled exception here.
            post = db.get(Post, uuid.UUID(post_id))
            if post is not None:
                notifications.notify_publish_failure(db, post)
        except Exception:
            db.rollback()
            logger.exception("Failed to record publish failure for post_id=%s", post_id)
            raise
        finally:
            db.close()


@celery_app.task(
    name="worker.publish_post",
    base=_PublishTask,
    autoretry_for=(publish_queue.PublishAttemptFailed,),
    retry_backoff=PUBLISH_RETRY_BACKOFF_BASE,
    retry_backoff_max=PUBLISH_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=PUBLISH_MAX_RETRIES,
)
def publish_post_task(post_id: str) -> None:
    """The actual publish Celery task Issue #31 asks for — deliberately
    thin. All the real logic (resolving target platforms, calling #30's
    SocialPublisher adapters, recording per-platform results) lives in
    apps/api/services/publish_queue.py, kept import-free of Celery so it
    stays unit-testable without any Celery/Redis machinery running (see
    that module's docstring). This wrapper's only job is to give that
    logic Celery's durable-queue + exponential-backoff-retry machinery —
    autoretry_for/retry_backoff, Celery's own built-in retry support —
    rather than a hand-rolled backoff loop.

    Approved posts are picked up here without any manual trigger: the
    pipeline's `publisher` node (packages/agents/pipeline/graph.py) calls
    publish_queue.enqueue_publish() — which is this task's .delay() —
    the moment a post reaches that stage, which happens automatically as
    part of resuming the graph from the human_review approve endpoint
    (apps/api/routers/review.py).
    """
    db = SessionLocal()
    try:
        publish_queue.publish_post(db, uuid.UUID(post_id))
        db.commit()
    except publish_queue.PublishAttemptFailed:
        # publish_post already wrote this attempt's per-platform
        # results/error onto the Post — commit that before propagating,
        # so it's visible even while retries are still in flight, then
        # let autoretry_for's wrapping catch this and schedule the retry.
        db.commit()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
