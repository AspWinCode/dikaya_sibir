from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from kombu import Exchange, Queue

from app.core.config import settings

celery_app = Celery(
    "nocode",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.worker.tasks.notifications",
        "app.worker.tasks.exports",
        "app.worker.tasks.sandbox",
        "app.worker.tasks.workflow",
        "app.worker.tasks.integration",
        "app.worker.tasks.documents",
        "app.worker.tasks.rules_schedule",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task routing
    task_queues=[
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("notifications", Exchange("notifications"), routing_key="notifications"),
        Queue("exports", Exchange("exports"), routing_key="exports"),
        Queue("sandbox", Exchange("sandbox"), routing_key="sandbox"),
        Queue("integration", Exchange("integration"), routing_key="integration"),
    ],
    task_default_queue="default",
    task_routes={
        "app.worker.tasks.notifications.*": {"queue": "notifications"},
        "app.worker.tasks.exports.*": {"queue": "exports"},
        "app.worker.tasks.sandbox.*": {"queue": "sandbox"},
        "app.worker.tasks.integration.*": {"queue": "integration"},
    },
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    # Result expiry
    result_expires=3600,
    # Sandbox tasks — hard time limit 113s (per architecture spec)
    task_time_limit=120,
    task_soft_time_limit=113,
    # Beat schedule — outbox poller runs every 10 seconds
    beat_schedule={
        "poll-outbox": {
            "task": "app.worker.tasks.integration.poll_outbox",
            "schedule": 10.0,  # seconds
            "options": {"queue": "integration"},
        },
        "close-overdue-filing-cases": {
            "task": "app.worker.tasks.documents.close_overdue_filing_cases",
            "schedule": crontab(hour=0, minute=15),  # once daily, just after midnight UTC
            "options": {"queue": "default"},
        },
        "evaluate-scheduled-rules": {
            "task": "app.worker.tasks.rules_schedule.evaluate_scheduled_rules",
            "schedule": crontab(minute=0),  # once an hour, on the hour (ТЗ 3.5.1 schedule rules)
            "options": {"queue": "sandbox"},
        },
    },
)


@worker_process_init.connect
def _dispose_inherited_db_pool(**kwargs: object) -> None:
    """Celery's prefork pool forks worker child processes *after*
    `app.core.database` has already been imported (via the `include=[...]`
    task modules above) and its module-level async engine/connection pool
    created in the parent process. fork() duplicates that pool object's
    Python state into each child, but the underlying asyncpg sockets and
    their internal protocol state are not forkable — every child starts
    out sharing file descriptors with the parent and with every sibling
    child, so two of them touching the "same" pooled connection collide
    with asyncpg's "another operation is in progress" (an operation one
    sibling issued races one issued by another on what is, at the OS
    level, the one socket they all inherited).

    Standard fix for async engines + Celery prefork: discard the inherited
    pool in each freshly-forked child so its first real query opens a
    genuinely new connection instead of reusing a shared one. `dispose()`
    on the sync-facing pool is deliberately used here (not the async
    `engine.dispose()`) — this hook runs before any event loop exists in
    the child, so there is nothing to await yet; dropping the pool's
    object references is enough, since nothing in it is actually usable
    post-fork regardless."""
    from app.core.database import engine

    engine.sync_engine.dispose()
