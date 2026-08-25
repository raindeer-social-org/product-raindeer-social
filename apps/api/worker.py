import logging
import uuid

from celery import Celery, Task

from apps.api.config import get_settings
from apps.api.config.database import SessionLocal
from apps.api.services import engagement_polling, publish_queue

settings = get_settings()

celery_app = Celery(
    "raindeer",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.broker_connection_retry_on_startup = True

# Issue #33: on a recurring schedule, poll engagement metrics for every
# published post's platform(s) and append an EngagementSnapshot row per
# poll. Runs every 15 minutes — frequent enough to build a meaningful
# time series without hammering the platform APIs (see
# ENGAGEMENT_POLL_INTERVAL_SECONDS below and
# apps/api/services/engagement_polling.py's module docstring for the
# rate-limit story). The actual selection/fetch/snapshot logic lives in
# that module, not here, so it's unit-testable without any Celery
# machinery — same split #29's beat_schedule (pipeline trigger) and #31's
# publish queue already use.
ENGAGEMENT_POLL_INTERVAL_SECONDS = 900.0

celery_app.conf.beat_schedule = {
    "poll-engagement": {
        "task": "worker.poll_engagement",
        "schedule": ENGAGEMENT_POLL_INTERVAL_SECONDS,
    },
}

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

# Issue #33's "rate limits must be respected" acceptance criterion, same
# mechanism and same reasoning as PUBLISH_* above: a rate-limited (or any
# other failed) engagement fetch raises EngagementPollFailed, and this is
# the cap/backoff schedule Celery retries it with, rather than a
# hand-rolled retry loop.
ENGAGEMENT_MAX_RETRIES = 5
ENGAGEMENT_RETRY_BACKOFF_BASE = 30
ENGAGEMENT_RETRY_BACKOFF_MAX = 600


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


@celery_app.task(name="worker.poll_engagement")
def poll_engagement_task() -> int:
    """Celery Beat entrypoint for Issue #33's engagement polling sweep.

    A thin wrapper, same shape as #29's trigger_due_pipelines_task:
    figures out which posts are due for a poll
    (engagement_polling.find_posts_due_for_polling — no Celery machinery
    needed for that query), then fans out one poll_post_engagement_task
    per post rather than polling all of them inline in this single task.
    That fan-out means one post's platform being rate-limited (and
    therefore retried with backoff, see poll_post_engagement_task below)
    never delays or blocks polling any other post in the same sweep.
    Returns the number of posts a poll was enqueued for.
    """
    db = SessionLocal()
    try:
        post_ids = engagement_polling.find_posts_due_for_polling(db)
    finally:
        db.close()

    for post_id in post_ids:
        poll_post_engagement_task.delay(str(post_id))
    return len(post_ids)


@celery_app.task(
    name="worker.poll_post_engagement",
    autoretry_for=(engagement_polling.EngagementPollFailed,),
    retry_backoff=ENGAGEMENT_RETRY_BACKOFF_BASE,
    retry_backoff_max=ENGAGEMENT_RETRY_BACKOFF_MAX,
    retry_jitter=True,
    max_retries=ENGAGEMENT_MAX_RETRIES,
)
def poll_post_engagement_task(post_id: str) -> None:
    """The actual per-post engagement poll Issue #33 asks for —
    deliberately thin, same split as publish_post_task above. All the
    real logic (resolving published platforms, calling #30's
    SocialPublisher.get_engagement() adapters, writing EngagementSnapshot
    rows) lives in apps/api/services/engagement_polling.py, kept
    import-free of Celery so it stays unit-testable without any
    Celery/Redis machinery running. This wrapper's only job is to give
    that logic Celery's exponential-backoff-retry machinery —
    autoretry_for/retry_backoff — so a rate-limited (or otherwise failed)
    platform fetch is backed off and retried later rather than hammered
    or left to crash the whole sweep.
    """
    db = SessionLocal()
    try:
        engagement_polling.poll_post_engagement(db, uuid.UUID(post_id))
        db.commit()
    except engagement_polling.EngagementPollFailed:
        # poll_post_engagement already committed a snapshot row for every
        # platform that succeeded on this attempt — commit that before
        # propagating, then let autoretry_for's wrapping catch this and
        # schedule the retry.
        db.commit()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
