import uuid

import structlog
from celery import Task, shared_task

logger = structlog.get_logger(__name__)


@shared_task(
    name="app.worker.tasks.notifications.deliver_rule_webhook",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def deliver_rule_webhook(
    self: Task,
    app_id: str,
    entity_id: str,
    record_id: str | None,
    execution_batch_id: str,
    url: str,
    method: str,
    payload: dict[str, object],
) -> dict[str, str]:
    """
    Fire one `call_webhook` rule action and record the outcome.

    Runs on the `notifications` queue — deliberately outside the sandbox
    worker, which has no business making outbound network calls of its own.
    The target URL still goes through app.core.http_client's SSRF guard
    since it is authored by an app builder, not a platform admin.
    """
    import asyncio

    from app.core.database import AsyncSessionLocal
    from app.core.http_client import send_webhook
    from app.models.logic import RuleWebhookDelivery

    result = send_webhook(url=url, method=method, payload=payload)

    async def _log() -> None:
        async with AsyncSessionLocal() as session:
            session.add(
                RuleWebhookDelivery(
                    app_id=uuid.UUID(app_id),
                    entity_id=uuid.UUID(entity_id),
                    record_id=uuid.UUID(record_id) if record_id else None,
                    execution_batch_id=uuid.UUID(execution_batch_id),
                    url=url,
                    method=method,
                    payload=payload,
                    status="delivered"
                    if result.success
                    else (
                        "blocked"
                        if result.error and result.error.startswith("Blocked:")
                        else "failed"
                    ),
                    status_code=result.status_code,
                    error=result.error,
                    attempt_count=self.request.retries + 1,
                )
            )
            await session.commit()

    asyncio.run(_log())

    if result.success:
        logger.info("rule_webhook_delivered", url=url, code=result.status_code)
        return {"status": "delivered"}

    if result.error and result.error.startswith("Blocked:"):
        logger.warning("rule_webhook_blocked", url=url, error=result.error)
        return {"status": "blocked", "error": result.error}

    logger.warning("rule_webhook_failed", url=url, error=result.error, code=result.status_code)
    if self.request.retries < self.max_retries:
        raise self.retry(exc=Exception(result.error or f"HTTP {result.status_code}"))
    return {"status": "exhausted", "error": result.error or ""}


@shared_task(
    name="app.worker.tasks.notifications.send_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
)
def send_email(
    self: object,
    to: str,
    subject: str,
    body_html: str,
    body_text: str = "",
) -> dict[str, str]:
    """Send a transactional email via SMTP."""
    import asyncio
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    import aiosmtplib

    from app.core.config import settings

    msg = MIMEMultipart("alternative")
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    async def _send() -> None:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_TLS,
        )

    asyncio.run(_send())
    logger.info("email_sent", to=to, subject=subject)
    return {"status": "sent", "to": to}


_EVENT_TITLES: dict[str, str] = {
    "approval_requested": "Требуется ваше согласование",
    "assigned": "Вам назначена задача",
    "state_changed": "Изменение состояния процесса",
    "cancelled": "Процесс отменён",
    "completed": "Процесс завершён",
}


@shared_task(name="app.worker.tasks.notifications.send_workflow_notification")
def send_workflow_notification(
    user_id: str,
    event: str,
    payload: dict[str, object],
) -> None:
    """Look up user email and send workflow event notification."""
    import asyncio

    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.identity import User

    async def _fetch_user() -> tuple[str, str] | None:
        async with AsyncSessionLocal() as session:
            row = await session.execute(select(User).where(User.id == uuid.UUID(user_id)))
            user = row.scalar_one_or_none()
            if user and user.email:
                return user.email, user.display_name
            return None

    result = asyncio.run(_fetch_user())
    if result is None:
        logger.warning("workflow_notification_no_user", user_id=user_id)
        return

    to_email, display_name = result
    workflow_name = str(payload.get("workflow_name", "Процесс"))
    state = str(payload.get("state", ""))
    record_id = str(payload.get("record_id", ""))

    title = _EVENT_TITLES.get(event, "Уведомление о процессе")
    subject = f"{title}: {workflow_name}"

    state_row = f"<p>Состояние: <strong>{state}</strong></p>" if state else ""
    record_row = (
        f"<p>Запись ID: <code style='font-size:12px'>{record_id}</code></p>" if record_id else ""
    )

    body_html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1a2340">
  <h2 style="color:#00205F;margin-bottom:12px">{title}</h2>
  <p>Здравствуйте, {display_name}!</p>
  <p>Процесс: <strong>{workflow_name}</strong></p>
  {state_row}
  {record_row}
  <p style="color:#888;margin-top:20px;font-size:13px">
    Войдите в систему для просмотра подробностей.
  </p>
</div>
"""

    send_email.apply_async(
        kwargs={"to": to_email, "subject": subject, "body_html": body_html},
        queue="notifications",
    )
    logger.info("workflow_notification_queued", user_id=user_id, event=event, to=to_email)
