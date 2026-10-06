import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.integration import (
    RotateSecretResponse,
    WebhookDeliveryRead,
    WebhookSubscriptionCreate,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.integration import WebhookNotFoundError, WebhookService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/apps/{app_id}/webhooks", tags=["integration"])


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")


# ==================================================================
# Subscriptions
# ==================================================================

@router.get("", response_model=list[WebhookSubscriptionRead])
async def list_webhooks(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    active_only: bool = Query(default=False),
) -> list[WebhookSubscriptionRead]:
    await _check_app(app_id, current_user, db)
    return await WebhookService(db).list_subscriptions(app_id, active_only=active_only)


class WebhookCreateResponse(WebhookSubscriptionRead):
    """Creation response includes the secret (shown only once)."""
    secret: str


@router.post("", response_model=WebhookCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    app_id: uuid.UUID,
    body: WebhookSubscriptionCreate,
    current_user: AuthDep,
    db: DbDep,
) -> WebhookCreateResponse:
    """
    Create a webhook subscription.

    The `secret` field in the response is the HMAC signing key —
    **store it immediately**, it will not be shown again.
    """
    await _check_app(app_id, current_user, db)
    sub_read, secret = await WebhookService(db).create_subscription(app_id, body)
    return WebhookCreateResponse(**sub_read.model_dump(), secret=secret)


@router.get("/{sub_id}", response_model=WebhookSubscriptionRead)
async def get_webhook(
    app_id: uuid.UUID,
    sub_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> WebhookSubscriptionRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WebhookService(db).get_subscription(app_id, sub_id)
    except WebhookNotFoundError as exc:
        raise _not_found(exc) from exc


@router.patch("/{sub_id}", response_model=WebhookSubscriptionRead)
async def update_webhook(
    app_id: uuid.UUID,
    sub_id: uuid.UUID,
    body: WebhookSubscriptionUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> WebhookSubscriptionRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WebhookService(db).update_subscription(app_id, sub_id, body)
    except WebhookNotFoundError as exc:
        raise _not_found(exc) from exc


@router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    app_id: uuid.UUID,
    sub_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await WebhookService(db).delete_subscription(app_id, sub_id)
    except WebhookNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post("/{sub_id}/rotate_secret", response_model=RotateSecretResponse)
async def rotate_secret(
    app_id: uuid.UUID,
    sub_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> RotateSecretResponse:
    """
    Regenerate the HMAC signing secret.

    The new secret is returned **once** — store it immediately.
    Old secret stops working immediately after rotation.
    """
    await _check_app(app_id, current_user, db)
    try:
        return await WebhookService(db).rotate_secret(app_id, sub_id)
    except WebhookNotFoundError as exc:
        raise _not_found(exc) from exc


# ==================================================================
# Delivery history
# ==================================================================

@router.get("/{sub_id}/deliveries", response_model=list[WebhookDeliveryRead])
async def list_deliveries(
    app_id: uuid.UUID,
    sub_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WebhookDeliveryRead]:
    await _check_app(app_id, current_user, db)
    try:
        await WebhookService(db).get_subscription(app_id, sub_id)
    except WebhookNotFoundError as exc:
        raise _not_found(exc) from exc
    return await WebhookService(db).list_deliveries(
        app_id, sub_id=sub_id, status=status_filter, limit=limit
    )
