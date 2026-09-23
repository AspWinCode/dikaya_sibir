"""Async email service using aiosmtplib."""
import structlog
from aiosmtplib import SMTP, SMTPException

from app.core.config import settings

logger = structlog.get_logger(__name__)


async def send_email(
    to: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
) -> bool:
    """Send a single email. Logs and swallows errors; returns True on success."""
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to

    if body_text:
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        use_ssl = settings.SMTP_TLS and settings.SMTP_PORT in (465, 9465)
        use_starttls = settings.SMTP_TLS and not use_ssl
        async with SMTP(
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            use_tls=use_ssl,
            start_tls=use_starttls,
            timeout=20,
        ) as smtp:
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            await smtp.send_message(msg)
        logger.info("email_sent", to=to, subject=subject)
        return True
    except (SMTPException, OSError, TimeoutError):
        logger.exception("email_send_failed", to=to, subject=subject)
        return False


async def send_via_template(
    db,
    code: str,
    to: str,
    context: dict,
    fallback_subject: str = "",
    fallback_html: str = "",
    fallback_text: str | None = None,
) -> bool:
    """Render a template by code and send. Falls back to inline content if the
    template is missing or fails to render."""
    from app.services.email_templates import EmailTemplateRenderError, EmailTemplateService
    try:
        rendered = await EmailTemplateService(db).render_by_code(code, context)
    except EmailTemplateRenderError:
        logger.exception("email_template_render_failed", code=code)
        rendered = None
    if rendered:
        return await send_email(to, rendered.subject, rendered.body_html, rendered.body_text)
    return await send_email(to, fallback_subject, fallback_html, fallback_text)


async def send_password_reset_email(
    to: str,
    display_name: str,
    reset_url: str,
    db=None,
) -> bool:
    if db is not None:
        return await send_via_template(
            db, "password_reset", to,
            {"display_name": display_name, "reset_url": reset_url},
            fallback_subject="Сброс пароля",
            fallback_html=f"<p>Здравствуйте, {display_name}!</p><p><a href=\"{reset_url}\">Сбросить пароль</a></p>",
        )
    subject = "Сброс пароля"
    html = (
        f"<p>Здравствуйте, {display_name}!</p>"
        "<p>Мы получили запрос на сброс пароля для вашего аккаунта.</p>"
        f"<p><a href=\"{reset_url}\">Сбросить пароль</a></p>"
        "<p>Ссылка действительна 1 час. Если вы не запрашивали сброс — просто проигнорируйте это письмо.</p>"
    )
    text = (
        f"Здравствуйте, {display_name}!\n\n"
        "Мы получили запрос на сброс пароля.\n"
        f"Перейдите по ссылке: {reset_url}\n"
        "Ссылка действительна 1 час.\n"
        "Если вы не запрашивали сброс — проигнорируйте это письмо."
    )
    return await send_email(to, subject, html, text)


async def send_invitation_email(
    to: str,
    display_name: str,
    temp_password: str,
    platform_url: str = "http://localhost:5173/editor",
    db=None,
) -> bool:
    if db is not None:
        return await send_via_template(
            db, "invitation", to,
            {"display_name": display_name, "email": to, "temp_password": temp_password, "platform_url": platform_url},
            fallback_subject="Приглашение на платформу",
            fallback_html=f"<p>Здравствуйте, {display_name}!</p><p>Email: {to}, пароль: {temp_password}</p>",
        )
    subject = "Приглашение на платформу"
    html = (
        f"<p>Здравствуйте, {display_name}!</p>"
        "<p>Вас пригласили на платформу бизнес-приложений.</p>"
        f"<p><b>Email:</b> {to}<br><b>Временный пароль:</b> {temp_password}</p>"
        f"<p>Войдите по ссылке: <a href=\"{platform_url}\">{platform_url}</a></p>"
        "<p>Смените пароль после первого входа.</p>"
    )
    text = (
        f"Здравствуйте, {display_name}!\n\n"
        f"Вас пригласили на платформу бизнес-приложений.\n"
        f"Email: {to}\nВременный пароль: {temp_password}\n"
        f"Войдите: {platform_url}\n"
        "Смените пароль после первого входа."
    )
    return await send_email(to, subject, html, text)
