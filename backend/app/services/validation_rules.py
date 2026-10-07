"""Synchronous, pre-commit validation rules (rule_type="validation").

Unlike automation/autofill rules — which run asynchronously, after the
triggering record is already committed, in the sandboxed Celery worker
(app/worker/tasks/sandbox.py) — validation rules run inline, in-process,
*before* the record is written, so a "block_save" action can actually
reject the write. This is why it's a separate rule_type and a separate
execution path rather than a branch of RuleService.evaluate_rules_for_event:
the two run at fundamentally different points in the request lifecycle.

Conditions may use a "lookup" expression (app/engine/lookup.py) to read
values from OTHER entities' records — e.g. "хватает ли материала по
рецепту" needs to read рецепты and номенклатура, not just the деталь
отчёта record being saved.
"""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.interpreter import ExecutionContext, RuleError, evaluate_conditions
from app.engine.lookup import RuleLookupError, resolve_lookups
from app.models.logic import Rule

logger = structlog.get_logger(__name__)


class ValidationBlockedError(Exception):
    """A validation rule's block_save action rejected the save."""

    def __init__(self, message: str, rule_id: uuid.UUID | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.rule_id = rule_id


class ValidationRuleService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def run(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        event: str,
        record_payload: dict,
        record_id: uuid.UUID | None = None,
        changed_fields: list[str] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """Raises ValidationBlockedError if any matching validation rule's
        block_save action fires. Read-only against the DB otherwise — never
        writes, so callers can run this before add()/flush() with nothing to
        roll back if it raises."""
        result = await self._db.execute(
            select(Rule)
            .where(
                Rule.app_id == app_id,
                Rule.entity_id == entity_id,
                Rule.rule_type == "validation",
                Rule.is_active.is_(True),
            )
            .order_by(Rule.priority.asc())
        )
        rules = list(result.scalars().all())
        if not rules:
            return

        ctx = ExecutionContext(
            record=record_payload,
            entity_id=entity_id,
            app_id=app_id,
            event=event,
            actor_id=actor_id,
            record_id=record_id,
            changed_fields=changed_fields or [],
        )

        for rule in rules:
            trigger_event = (rule.trigger or {}).get("event", "")
            if (
                trigger_event
                and trigger_event != event
                and not (trigger_event == "field.changed" and event == "record.updated")
            ):
                continue
            if trigger_event == "field.changed":
                watch_fields = set((rule.trigger or {}).get("watch_fields", []))
                if watch_fields and not (watch_fields & set(ctx.changed_fields)):
                    continue

            try:
                resolved_conditions = await resolve_lookups(rule.conditions, self._db, ctx)
                matched = evaluate_conditions(resolved_conditions, ctx)
            except (RuleError, RuleLookupError) as exc:
                logger.warning(
                    "validation_rule_error",
                    rule_id=str(rule.id),
                    entity_id=str(entity_id),
                    error=str(exc),
                )
                continue
            if not matched:
                continue

            for action in rule.actions or []:
                if action.get("type") == "block_save":
                    message = action.get("message") or "Сохранение отклонено правилом проверки"
                    logger.info(
                        "validation_rule_blocked",
                        rule_id=str(rule.id),
                        entity_id=str(entity_id),
                    )
                    raise ValidationBlockedError(message, rule_id=rule.id)
