"""
Integration Celery tasks.

poll_outbox      — Beat task (every 10 s). Reads pending outbox events,
                   fans them out to matching webhook subscriptions, enqueues
                   deliver_webhook per delivery row. Uses FOR UPDATE SKIP LOCKED
                   so multiple beat instances never double-process.

deliver_webhook  — Executes one HTTP delivery attempt. Retries with exponential
                   backoff (60 s / 5 min / 30 min). Marks delivery exhausted
                   after max_retries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from celery import shared_task

from app.core.metrics import outbox_events_processed, webhook_deliveries

logger = structlog.get_logger(__name__)

# Backoff schedule in seconds: attempt 0→1 wait 60s, 1→2 wait 300s, 2→3 wait 1800s
_BACKOFF = [60, 300, 1800]


# ------------------------------------------------------------------
# Outbox poller (beat, every 10 s)
# ------------------------------------------------------------------


@shared_task(
    name="app.worker.tasks.integration.poll_outbox",
    bind=True,
    max_retries=0,
    acks_late=True,
)
def poll_outbox(self: object) -> dict:
    """
    Poll integration.outbox for pending events and fan out to webhook deliveries.

    Steps:
      1. SELECT … FOR UPDATE SKIP LOCKED LIMIT 100
      2. For each event find active subscriptions matching the event_type
      3. Create WebhookDelivery rows
      4. Enqueue deliver_webhook tasks
      5. Mark outbox rows as processed
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.core.http_client import subscription_matches
        from app.models.integration import Outbox, WebhookDelivery, WebhookSubscription

        dispatched = 0

        async with AsyncSessionLocal() as session, session.begin():
            # 1. Lock pending rows
            stmt = (
                select(Outbox)
                .where(
                    Outbox.status == "pending",
                    Outbox.scheduled_at <= datetime.now(UTC),
                )
                .order_by(Outbox.created_at)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                return {"dispatched": 0}

            # Collect all distinct app_ids to load subscriptions once
            app_ids = {e.app_id for e in events}
            subs_result = await session.execute(
                select(WebhookSubscription).where(
                    WebhookSubscription.app_id.in_(app_ids),
                    WebhookSubscription.is_active.is_(True),
                )
            )
            subscriptions = subs_result.scalars().all()

            # 2–4. Fan out
            for event in events:
                matching = [
                    s
                    for s in subscriptions
                    if s.app_id == event.app_id
                    and subscription_matches(list(s.events), event.event_type)
                ]
                for sub in matching:
                    delivery = WebhookDelivery(
                        subscription_id=sub.id,
                        app_id=event.app_id,
                        event_type=event.event_type,
                        payload=dict(event.payload),
                        outbox_id=event.id,
                        status="pending",
                    )
                    session.add(delivery)
                    await session.flush()  # get delivery.id

                    deliver_webhook.apply_async(
                        kwargs={"delivery_id": str(delivery.id)},
                        queue="integration",
                    )
                    dispatched += 1

                # 5. Mark processed
                event.status = "processed"
                event.processed_at = datetime.now(UTC)

        outbox_events_processed.inc(len(events))
        logger.info("outbox_poll_done", events=len(events), dispatched=dispatched)
        return {"events": len(events), "dispatched": dispatched}

    return asyncio.run(_run())


# ------------------------------------------------------------------
# Webhook delivery (with retry)
# ------------------------------------------------------------------


@shared_task(
    name="app.worker.tasks.integration.deliver_webhook",
    bind=True,
    max_retries=0,  # Manual retry logic below (backoff schedule)
    acks_late=True,
    time_limit=120,
    soft_time_limit=113,
)
def deliver_webhook(self: object, delivery_id: str) -> dict:
    """
    Execute one webhook delivery attempt.

    On success  → status = 'delivered'
    On failure  → status = 'failed', schedule retry if attempts < max_retries
    Exhausted   → status = 'exhausted' (no more retries)
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.core.http_client import deliver as http_deliver
        from app.models.integration import WebhookDelivery, WebhookSubscription

        async with AsyncSessionLocal() as session, session.begin():
            d_res = await session.execute(
                select(WebhookDelivery).where(WebhookDelivery.id == uuid.UUID(delivery_id))
            )
            delivery: WebhookDelivery | None = d_res.scalar_one_or_none()
            if delivery is None:
                logger.warning("delivery_not_found", delivery_id=delivery_id)
                return {"status": "skipped", "reason": "not_found"}

            sub_res = await session.execute(
                select(WebhookSubscription).where(
                    WebhookSubscription.id == delivery.subscription_id
                )
            )
            sub: WebhookSubscription | None = sub_res.scalar_one_or_none()
            if sub is None or not sub.is_active:
                delivery.status = "exhausted"
                delivery.error = "Subscription deleted or deactivated"
                return {"status": "exhausted"}

            # Make the HTTP call (sync, safe inside asyncio.run)
            result = http_deliver(
                target_url=sub.target_url,
                payload=dict(delivery.payload),
                event_type=delivery.event_type,
                delivery_id=delivery_id,
                secret=sub.secret,
                custom_headers=dict(sub.custom_headers) or None,
                timeout_seconds=sub.timeout_seconds,
            )

            delivery.attempt_count += 1
            delivery.last_response_code = result.status_code
            delivery.last_response_body = result.response_body

            if result.success:
                delivery.status = "delivered"
                delivery.delivered_at = datetime.now(UTC)
                webhook_deliveries.labels(status="delivered").inc()
                logger.info("webhook_delivered", delivery_id=delivery_id, code=result.status_code)
                return {"status": "delivered"}

            # Failed — schedule retry or mark exhausted
            delivery.error = result.error or f"HTTP {result.status_code}"
            if delivery.attempt_count < sub.max_retries:
                backoff = _BACKOFF[min(delivery.attempt_count - 1, len(_BACKOFF) - 1)]
                delivery.status = "failed"
                delivery.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff)
                webhook_deliveries.labels(status="failed").inc()
                logger.warning(
                    "webhook_failed_will_retry",
                    delivery_id=delivery_id,
                    attempt=delivery.attempt_count,
                    backoff_s=backoff,
                )

                deliver_webhook.apply_async(
                    kwargs={"delivery_id": delivery_id},
                    countdown=backoff,
                    queue="integration",
                )
            else:
                delivery.status = "exhausted"
                webhook_deliveries.labels(status="exhausted").inc()
                logger.error(
                    "webhook_exhausted",
                    delivery_id=delivery_id,
                    attempts=delivery.attempt_count,
                )

            return {"status": delivery.status}

    return asyncio.run(_run())
