"""
Integration services.

OutboxWriter  — writes events to integration.outbox within the caller's
                transaction (publish/subscribe pattern backbone).

WebhookService — CRUD for webhook subscriptions + delivery history queries.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http_client import generate_secret
from app.models.integration import Outbox, WebhookDelivery, WebhookSubscription
from app.schemas.integration import (
    RotateSecretResponse,
    WebhookDeliveryRead,
    WebhookSubscriptionCreate,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Errors
# ------------------------------------------------------------------


class WebhookNotFoundError(Exception):
    pass


# ------------------------------------------------------------------
# Outbox writer
# ------------------------------------------------------------------


class OutboxWriter:
    """
    Write events to the transactional outbox.

    Call within an open AsyncSession — the INSERT is part of the caller's
    transaction so it commits or rolls back atomically with the triggering
    mutation.

    Usage:
        async with session.begin():
            record = Record(...)
            session.add(record)
            await OutboxWriter.publish(
                session, app_id, "record.created",
                {"record_id": str(record.id), ...},
                dedup_key=f"record.created:{record.id}",
            )
    """

    @staticmethod
    async def publish(
        db: AsyncSession,
        app_id: uuid.UUID,
        event_type: str,
        payload: dict[str, Any],
        dedup_key: str | None = None,
    ) -> Outbox:
        entry = Outbox(
            app_id=app_id,
            event_type=event_type,
            payload=payload,
            dedup_key=dedup_key or f"{event_type}:{uuid.uuid4()}",
            status="pending",
        )
        db.add(entry)
        # Do NOT flush/commit — caller owns the transaction
        return entry


# ------------------------------------------------------------------
# Webhook service
# ------------------------------------------------------------------


class WebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ---- Subscriptions ----

    async def list_subscriptions(
        self, app_id: uuid.UUID, active_only: bool = False
    ) -> list[WebhookSubscriptionRead]:
        stmt = (
            select(WebhookSubscription)
            .where(WebhookSubscription.app_id == app_id)
            .order_by(WebhookSubscription.created_at)
        )
        if active_only:
            stmt = stmt.where(WebhookSubscription.is_active.is_(True))
        result = await self._db.execute(stmt)
        return [WebhookSubscriptionRead.model_validate(s) for s in result.scalars()]

    async def get_subscription(
        self, app_id: uuid.UUID, sub_id: uuid.UUID
    ) -> WebhookSubscriptionRead:
        sub = await self._fetch(app_id, sub_id)
        return WebhookSubscriptionRead.model_validate(sub)

    async def create_subscription(
        self, app_id: uuid.UUID, data: WebhookSubscriptionCreate
    ) -> tuple[WebhookSubscriptionRead, str]:
        """Returns (read_model, plaintext_secret). Secret shown only once."""
        secret = generate_secret()
        sub = WebhookSubscription(
            app_id=app_id,
            name=data.name,
            target_url=data.target_url,
            events=data.events,
            secret=secret,
            is_active=True,
            custom_headers=data.custom_headers,
            timeout_seconds=data.timeout_seconds,
            max_retries=data.max_retries,
        )
        self._db.add(sub)
        await self._db.flush()
        logger.info("webhook_subscription_created", sub_id=str(sub.id), app_id=str(app_id))
        return WebhookSubscriptionRead.model_validate(sub), secret

    async def update_subscription(
        self, app_id: uuid.UUID, sub_id: uuid.UUID, data: WebhookSubscriptionUpdate
    ) -> WebhookSubscriptionRead:
        sub = await self._fetch(app_id, sub_id)
        if data.name is not None:
            sub.name = data.name
        if data.target_url is not None:
            sub.target_url = data.target_url
        if data.events is not None:
            sub.events = data.events
        if data.is_active is not None:
            sub.is_active = data.is_active
        if data.custom_headers is not None:
            sub.custom_headers = data.custom_headers
        if data.timeout_seconds is not None:
            sub.timeout_seconds = data.timeout_seconds
        if data.max_retries is not None:
            sub.max_retries = data.max_retries
        await self._db.flush()
        return WebhookSubscriptionRead.model_validate(sub)

    async def delete_subscription(self, app_id: uuid.UUID, sub_id: uuid.UUID) -> None:
        sub = await self._fetch(app_id, sub_id)
        await self._db.delete(sub)
        await self._db.flush()

    async def rotate_secret(self, app_id: uuid.UUID, sub_id: uuid.UUID) -> RotateSecretResponse:
        sub = await self._fetch(app_id, sub_id)
        new_secret = generate_secret()
        sub.secret = new_secret
        await self._db.flush()
        logger.info("webhook_secret_rotated", sub_id=str(sub_id))
        return RotateSecretResponse(id=sub.id, secret=new_secret)

    # ---- Delivery history ----

    async def list_deliveries(
        self,
        app_id: uuid.UUID,
        sub_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[WebhookDeliveryRead]:
        stmt = (
            select(WebhookDelivery)
            .where(WebhookDelivery.app_id == app_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        if sub_id:
            stmt = stmt.where(WebhookDelivery.subscription_id == sub_id)
        if status:
            stmt = stmt.where(WebhookDelivery.status == status)
        result = await self._db.execute(stmt)
        return [WebhookDeliveryRead.model_validate(d) for d in result.scalars()]

    # ---- Internals ----

    async def _fetch(self, app_id: uuid.UUID, sub_id: uuid.UUID) -> WebhookSubscription:
        result = await self._db.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.id == sub_id,
                WebhookSubscription.app_id == app_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            raise WebhookNotFoundError(str(sub_id))
        return sub
