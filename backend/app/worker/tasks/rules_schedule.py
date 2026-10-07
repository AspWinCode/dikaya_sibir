"""Scheduled rule sweep (ТЗ 3.5.1 "Расчёт"/"Уведомление": работа по
расписанию, а не только по событию — «ежемесячная амортизация»,
«напоминание за 3 дня до срока»).

Runs hourly via Celery beat (see app/worker/celery_app.py). A cron-kind
rule only ever sees this sweep's minute (0), so its `minute` field is
effectively binary: "0" fires on the hour, anything else never fires — no
sub-hour granularity. A relative_date-kind rule is checked once a day, at
the UTC-midnight tick, to avoid firing the same reminder more than once.

Rules matching the same entity+tick are batched into one
execute_rules_batch call together, same as the event-driven path in
RuleService.evaluate_rules_for_event, so priority-based conflict
resolution (ТЗ 3.5.4) applies here too.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from celery import shared_task

logger = structlog.get_logger(__name__)


def _cron_field_matches(spec: str, value: int) -> bool:
    if spec == "*":
        return True
    try:
        allowed = {int(p.strip()) for p in spec.split(",")}
    except ValueError:
        return False
    return value in allowed


def _cron_matches_now(cron: dict[str, Any], now: datetime) -> bool:
    return (
        _cron_field_matches(cron.get("minute", "0"), now.minute)
        and _cron_field_matches(cron.get("hour", "0"), now.hour)
        and _cron_field_matches(cron.get("day_of_month", "*"), now.day)
        and _cron_field_matches(cron.get("month_of_year", "*"), now.month)
        # crontab convention: 0=Sunday..6=Saturday; Python's Monday=0 needs remapping.
        and _cron_field_matches(cron.get("day_of_week", "*"), (now.isoweekday()) % 7)
    )


def _parse_date(value: object) -> date | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value[:10]).date()
    except ValueError:
        return None


@shared_task(
    name="app.worker.tasks.rules_schedule.evaluate_scheduled_rules",
    bind=True,
    max_retries=0,  # a missed tick just waits for the next one — retrying could double-fire
    acks_late=True,
)
def evaluate_scheduled_rules(self: object) -> dict:
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.data import Record
        from app.services.rules import RuleService
        from app.worker.tasks.sandbox import execute_rules_batch

        now = datetime.now(UTC)
        today = now.date()
        dispatched = 0

        async with AsyncSessionLocal() as session:
            rules = await RuleService(session).get_active_schedule_rules()

            # Which rules actually fire on this tick, grouped by entity.
            firing_by_entity: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
            for rule in rules:
                trigger = rule["trigger"] or {}
                kind = trigger.get("schedule_kind")
                if kind == "cron":
                    if _cron_matches_now(trigger.get("cron") or {}, now):
                        firing_by_entity[rule["entity_id"]].append(rule)
                elif kind == "relative_date" and now.hour == 0:
                    firing_by_entity[rule["entity_id"]].append(rule)

            for entity_id, entity_rules in firing_by_entity.items():
                records = (
                    (
                        await session.execute(
                            select(Record).where(
                                Record.entity_id == entity_id, Record.is_deleted.is_(False)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if not records:
                    continue

                for record in records:
                    matching = []
                    for rule in entity_rules:
                        trigger = rule["trigger"] or {}
                        if trigger.get("schedule_kind") == "relative_date":
                            rel = trigger.get("relative_date") or {}
                            record_date = _parse_date(record.payload.get(rel.get("date_field", "")))
                            target = today - timedelta(days=rel.get("offset_days", 0))
                            if record_date != target:
                                continue
                        matching.append(rule)
                    if not matching:
                        continue

                    matching.sort(key=lambda r: r["priority"])
                    execute_rules_batch.apply_async(
                        kwargs={
                            "rules": [
                                {
                                    "id": str(r["id"]),
                                    "trigger": r["trigger"],
                                    "conditions": r["conditions"],
                                    "actions": r["actions"],
                                    "priority": r["priority"],
                                }
                                for r in matching
                            ],
                            "context": {
                                "record": record.payload,
                                "record_id": str(record.id),
                                "entity_id": str(entity_id),
                                "app_id": str(matching[0]["app_id"]),
                                "event": "schedule",
                                "changed_fields": [],
                                "actor_id": None,
                            },
                            "execution_batch_id": str(uuid.uuid4()),
                        },
                        queue="sandbox",
                    )
                    dispatched += 1

        logger.info("scheduled_rules_swept", rule_count=len(rules), dispatched=dispatched)
        return {"dispatched": dispatched}

    return asyncio.run(_run())
