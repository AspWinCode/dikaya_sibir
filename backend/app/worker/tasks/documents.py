"""Filing case auto-closure (ТЗ 3.10.2): daily sweep that closes any open
case past its close_by date and notifies the responsible user."""

import structlog
from celery import shared_task

logger = structlog.get_logger(__name__)


@shared_task(
    name="app.worker.tasks.documents.close_overdue_filing_cases",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    acks_late=True,
)
def close_overdue_filing_cases(self: object) -> dict:
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.identity import User
        from app.services.registrar import RegistrarService

        closed_count = 0
        async with AsyncSessionLocal() as session:
            cases = await RegistrarService(session).close_overdue_cases()
            closed_count = len(cases)

            for case in cases:
                if not case.responsible_user_id:
                    continue
                user_result = await session.execute(
                    select(User).where(User.id == case.responsible_user_id)
                )
                user = user_result.scalar_one_or_none()
                if not user:
                    continue
                from app.worker.tasks.notifications import send_email

                send_email.apply_async(
                    kwargs={
                        "to": user.email,
                        "subject": f"Дело «{case.title}» закрыто по истечении срока",
                        "body_html": (
                            f"<p>Дело <b>{case.index_code} — {case.title}</b> автоматически "
                            f"закрыто {case.closed_at:%d.%m.%Y}, так как истёк "
                            "установленный срок.</p>"
                        ),
                    },
                    queue="notifications",
                )

            await session.commit()

        logger.info("filing_cases_auto_closed", count=closed_count)
        return {"closed": closed_count}

    return asyncio.run(_run())
