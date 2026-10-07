"""Keeps logic.rule_execution_log's monthly partitions ahead of the
current date. The table is partitioned by month (see
alembic/versions/0004_logic_rules.py) but nothing ever created new
partitions as time passed — 0004 only seeded partitions through 2026-06,
and every rule execution after that silently lost its audit-log row
(found via manual QA against production; backfilled in
alembic/versions/0046_rule_execution_log_partitions.py). This task is
the actual "scheduled job" 0004's own comment said would add more."""

import structlog
from celery import shared_task

logger = structlog.get_logger(__name__)

# How far ahead to keep partitions created — generous on purpose so a
# missed/delayed beat run (worker downtime, etc.) doesn't reopen the gap.
_MONTHS_AHEAD = 6


@shared_task(
    name="app.worker.tasks.partitions.ensure_rule_execution_log_partitions",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    acks_late=True,
)
def ensure_rule_execution_log_partitions(self: object) -> dict:
    import asyncio

    async def _run() -> dict:
        from datetime import UTC, datetime

        from sqlalchemy import text

        from app.core.database import AsyncSessionLocal

        today = datetime.now(UTC)
        year, month = today.year, today.month
        created = []
        async with AsyncSessionLocal() as session:
            for _ in range(_MONTHS_AHEAD + 1):
                next_year = year + (1 if month == 12 else 0)
                next_month = 1 if month == 12 else month + 1
                name = f"rule_execution_log_{year}_{month:02d}"
                await session.execute(
                    text(f"""
                        CREATE TABLE IF NOT EXISTS logic.{name}
                        PARTITION OF logic.rule_execution_log
                        FOR VALUES FROM ('{year}-{month:02d}-01')
                        TO ('{next_year}-{next_month:02d}-01')
                    """)
                )
                created.append(name)
                year, month = next_year, next_month
            await session.commit()
        logger.info("rule_execution_log_partitions_ensured", partitions=created)
        return {"ensured": created}

    return asyncio.run(_run())
