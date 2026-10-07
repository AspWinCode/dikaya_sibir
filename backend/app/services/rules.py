"""RuleService: CRUD, cycle detection, dry-run, trigger dispatch."""
import time
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.graph import (
    build_dependency_graph,
    extract_rule_nodes,
    find_cycles,
)
from app.engine.interpreter import ExecutionContext, ExecutionResult, run_rule
from app.models.data import Record
from app.models.logic import Rule, RuleConflictLog, RuleExecutionLog, RuleWebhookDelivery
from app.schemas.common import CursorPage
from app.schemas.rules import (
    MAX_STEPS,
    CycleCheckResponse,
    ProcessStepCreate,
    ProcessStepRead,
    ProcessStepUpdate,
    RuleConflictLogRead,
    RuleCreate,
    RuleExecutionLogRead,
    RuleRead,
    RuleTestRequest,
    RuleTestResponse,
    RuleUpdate,
    RuleWebhookDeliveryRead,
    _validate_action_node,
    ensure_step_ids,
    node_to_step,
    step_to_node,
)

logger = structlog.get_logger(__name__)


class RuleNotFoundError(Exception):
    pass


class RuleCycleError(Exception):
    def __init__(self, cycles: list[list[str]]) -> None:
        self.cycles = cycles
        super().__init__(f"Rule creates a dependency cycle: {cycles}")


class StepNotFoundError(Exception):
    pass


class StepValidationError(Exception):
    pass


class RuleService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_rules(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        active_only: bool = False,
    ) -> list[RuleRead]:
        stmt = select(Rule).where(Rule.app_id == app_id).order_by(Rule.priority.asc(), Rule.created_at.asc())
        if entity_id:
            stmt = stmt.where(Rule.entity_id == entity_id)
        if active_only:
            stmt = stmt.where(Rule.is_active.is_(True))
        result = await self._db.execute(stmt)
        return [RuleRead.model_validate(r) for r in result.scalars()]

    async def get_rule(self, app_id: uuid.UUID, rule_id: uuid.UUID) -> RuleRead:
        rule = await self._fetch(app_id, rule_id)
        return RuleRead.model_validate(rule)

    async def create_rule(
        self, app_id: uuid.UUID, data: RuleCreate, creator_id: uuid.UUID | None = None
    ) -> RuleRead:
        rule = Rule(
            app_id=app_id,
            entity_id=data.entity_id,
            name=data.name,
            description=data.description,
            rule_type=data.rule_type.value,
            trigger=data.trigger.model_dump(),
            conditions=data.conditions,
            actions=data.actions,
            priority=data.priority,
            created_by=creator_id,
            is_active=False,  # Rules start inactive; must be explicitly activated
        )
        self._db.add(rule)
        await self._db.flush()
        logger.info("rule_created", rule_id=str(rule.id), app_id=str(app_id))
        return RuleRead.model_validate(rule)

    async def update_rule(
        self, app_id: uuid.UUID, rule_id: uuid.UUID, data: RuleUpdate
    ) -> RuleRead:
        rule = await self._fetch(app_id, rule_id)

        if data.name is not None:
            rule.name = data.name
        if data.description is not None:
            rule.description = data.description
        if data.rule_type is not None:
            rule.rule_type = data.rule_type.value
        if data.trigger is not None:
            rule.trigger = data.trigger.model_dump()
        if data.conditions is not None:
            rule.conditions = data.conditions
        if data.actions is not None:
            rule.actions = data.actions
        if data.priority is not None:
            rule.priority = data.priority
        if data.is_active is not None:
            if data.is_active and not rule.is_active:
                # Re-check cycles when re-activating
                await self._assert_no_cycles(app_id, rule_id)
            rule.is_active = data.is_active

        rule.version += 1
        await self._db.flush()
        await self._db.refresh(rule, attribute_names=["updated_at"])
        return RuleRead.model_validate(rule)

    async def delete_rule(self, app_id: uuid.UUID, rule_id: uuid.UUID) -> None:
        rule = await self._fetch(app_id, rule_id)
        await self._db.delete(rule)
        await self._db.flush()

    async def activate_rule(self, app_id: uuid.UUID, rule_id: uuid.UUID) -> RuleRead:
        """Enable a rule. Fails if activation would introduce a dependency cycle."""
        await self._assert_no_cycles(app_id, rule_id)
        rule = await self._fetch(app_id, rule_id)
        rule.is_active = True
        await self._db.flush()
        await self._db.refresh(rule, attribute_names=["updated_at"])
        logger.info("rule_activated", rule_id=str(rule_id))
        return RuleRead.model_validate(rule)

    async def deactivate_rule(self, app_id: uuid.UUID, rule_id: uuid.UUID) -> RuleRead:
        rule = await self._fetch(app_id, rule_id)
        rule.is_active = False
        await self._db.flush()
        await self._db.refresh(rule, attribute_names=["updated_at"])
        return RuleRead.model_validate(rule)

    # ------------------------------------------------------------------
    # Process steps (ordered view over rule.actions)
    # ------------------------------------------------------------------

    async def list_steps(self, app_id: uuid.UUID, rule_id: uuid.UUID) -> list[ProcessStepRead]:
        rule = await self._fetch(app_id, rule_id)
        actions, changed = ensure_step_ids(rule.actions or [])
        if changed:
            rule.actions = actions  # persist backfilled ids
            await self._db.flush()
        return [node_to_step(n, i) for i, n in enumerate(actions)]

    async def add_step(
        self, app_id: uuid.UUID, rule_id: uuid.UUID, data: ProcessStepCreate
    ) -> ProcessStepRead:
        rule = await self._fetch(app_id, rule_id)
        actions, _ = ensure_step_ids(rule.actions or [])
        if len(actions) >= MAX_STEPS:
            raise StepValidationError(f"Rule exceeds the maximum of {MAX_STEPS} steps")
        node = step_to_node(data.type, data.config)
        try:
            _validate_action_node(node)
        except ValueError as exc:
            raise StepValidationError(str(exc)) from exc
        actions.append(node)
        rule.actions = actions
        rule.version += 1
        await self._db.flush()
        logger.info("rule_step_added", rule_id=str(rule_id), step_type=data.type)
        return node_to_step(node, len(actions) - 1)

    async def update_step(
        self, app_id: uuid.UUID, rule_id: uuid.UUID, step_id: str, data: ProcessStepUpdate
    ) -> ProcessStepRead:
        rule = await self._fetch(app_id, rule_id)
        actions, _ = ensure_step_ids(rule.actions or [])
        idx = next((i for i, n in enumerate(actions) if str(n.get("id")) == step_id), None)
        if idx is None:
            raise StepNotFoundError(step_id)
        current = actions[idx]
        new_type = data.type if data.type is not None else str(current.get("type"))
        new_config = (
            data.config
            if data.config is not None
            else {k: v for k, v in current.items() if k not in ("id", "type")}
        )
        node = step_to_node(new_type, new_config, step_id=step_id)
        try:
            _validate_action_node(node)
        except ValueError as exc:
            raise StepValidationError(str(exc)) from exc
        actions[idx] = node
        rule.actions = actions
        rule.version += 1
        await self._db.flush()
        return node_to_step(node, idx)

    async def delete_step(self, app_id: uuid.UUID, rule_id: uuid.UUID, step_id: str) -> None:
        rule = await self._fetch(app_id, rule_id)
        actions, _ = ensure_step_ids(rule.actions or [])
        remaining = [n for n in actions if str(n.get("id")) != step_id]
        if len(remaining) == len(actions):
            raise StepNotFoundError(step_id)
        rule.actions = remaining
        rule.version += 1
        await self._db.flush()

    async def reorder_steps(
        self, app_id: uuid.UUID, rule_id: uuid.UUID, step_ids: list[str]
    ) -> list[ProcessStepRead]:
        rule = await self._fetch(app_id, rule_id)
        actions, _ = ensure_step_ids(rule.actions or [])
        by_id = {str(n.get("id")): n for n in actions}
        if set(step_ids) != set(by_id.keys()):
            raise StepValidationError("step_ids must be a permutation of the current step ids")
        reordered = [by_id[sid] for sid in step_ids]
        rule.actions = reordered
        rule.version += 1
        await self._db.flush()
        return [node_to_step(n, i) for i, n in enumerate(reordered)]

    # ------------------------------------------------------------------
    # Cycle detection
    # ------------------------------------------------------------------

    async def check_cycles(self, app_id: uuid.UUID) -> CycleCheckResponse:
        rules_raw = await self._get_rules_raw(app_id, active_only=False)
        graph = build_dependency_graph(extract_rule_nodes(rules_raw))
        cycles = find_cycles(graph)
        return CycleCheckResponse(has_cycles=bool(cycles), cycles=cycles)

    # ------------------------------------------------------------------
    # Dry-run (test without persisting)
    # ------------------------------------------------------------------

    async def test_rule(
        self,
        app_id: uuid.UUID,
        rule_id: uuid.UUID,
        req: RuleTestRequest,
    ) -> RuleTestResponse:
        rule = await self._fetch(app_id, rule_id)
        ctx = ExecutionContext(
            record=dict(req.record_payload),
            entity_id=rule.entity_id,
            app_id=app_id,
            event=req.event,
            changed_fields=req.changed_fields,
        )
        result = run_rule(rule.trigger, rule.conditions, rule.actions, ctx)
        return RuleTestResponse(
            matched=result.matched,
            field_mutations=result.field_mutations,
            records_to_create=result.records_to_create,
            notifications=result.notifications,
            webhooks=result.webhooks,
            errors=result.errors,
        )

    # ------------------------------------------------------------------
    # Trigger evaluation (called from record endpoints on write events)
    # ------------------------------------------------------------------

    async def evaluate_rules_for_event(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        record_payload: dict,
        event: str,
        changed_fields: list[str] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> str | None:
        """
        Evaluate all active rules for this entity + event as ONE batch.

        All matching rules must be evaluated together (not as independent
        Celery tasks) for priority-based conflict resolution to be
        deterministic (ТЗ 3.5.4): with N separate tasks, Celery gives no
        guarantee about execution order, so "higher priority wins" could not
        actually be enforced — whichever task happened to finish last would
        win instead.

        Returns the dispatched task's id (or None if no active rules match),
        so it stays awaitable/observable the same way the old list did for a
        single-rule caller, while giving conflict detection visibility into
        every rule's proposed mutations before any of them is persisted.
        """
        rules_raw = await self._get_rules_raw(app_id, active_only=True, entity_id=entity_id)
        # Validation rules run synchronously in-process, *before* the write
        # commits (ValidationRuleService — the only place that resolves
        # their `lookup` condition nodes and knows what `block_save`
        # means), never via this async batch. The pure interpreter this
        # batch runs through (app/engine/interpreter.py / expressions.py)
        # has no "lookup" expression type and no "block_save" action — a
        # validation rule dispatched here always errors, either on an
        # unresolved lookup (every validation rule that uses one — which is
        # most of them, see app/engine/lookup.py) or on the action itself.
        rules_raw = [r for r in rules_raw if r.get("rule_type") != "validation"]
        if not rules_raw:
            return None

        from app.worker.tasks.sandbox import execute_rules_batch

        sorted_rules = sorted(rules_raw, key=lambda r: r.get("priority", 100))
        task = execute_rules_batch.apply_async(
            kwargs={
                "rules": [
                    {
                        "id": str(r["id"]),
                        "trigger": r["trigger"],
                        "conditions": r["conditions"],
                        "actions": r["actions"],
                        "priority": r.get("priority", 100),
                    }
                    for r in sorted_rules
                ],
                "context": {
                    "record": record_payload,
                    "record_id": str(record_id),
                    "entity_id": str(entity_id),
                    "app_id": str(app_id),
                    "event": event,
                    "changed_fields": changed_fields or [],
                    "actor_id": str(actor_id) if actor_id else None,
                },
                "execution_batch_id": str(uuid.uuid4()),
            },
            queue="sandbox",
        )
        return task.id

    # ------------------------------------------------------------------
    # Execution log
    # ------------------------------------------------------------------

    async def list_logs(
        self,
        app_id: uuid.UUID,
        rule_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[RuleExecutionLogRead]:
        stmt = (
            select(RuleExecutionLog)
            .where(RuleExecutionLog.app_id == app_id)
            .order_by(RuleExecutionLog.executed_at.desc())
            .limit(limit)
        )
        if rule_id:
            stmt = stmt.where(RuleExecutionLog.rule_id == rule_id)
        result = await self._db.execute(stmt)
        return [RuleExecutionLogRead.model_validate(log) for log in result.scalars()]

    async def list_conflicts(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[RuleConflictLogRead]:
        stmt = (
            select(RuleConflictLog)
            .where(RuleConflictLog.app_id == app_id)
            .order_by(RuleConflictLog.detected_at.desc())
            .limit(limit)
        )
        if entity_id:
            stmt = stmt.where(RuleConflictLog.entity_id == entity_id)
        result = await self._db.execute(stmt)
        return [RuleConflictLogRead.model_validate(log) for log in result.scalars()]

    async def list_webhook_deliveries(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[RuleWebhookDeliveryRead]:
        stmt = (
            select(RuleWebhookDelivery)
            .where(RuleWebhookDelivery.app_id == app_id)
            .order_by(RuleWebhookDelivery.created_at.desc())
            .limit(limit)
        )
        if entity_id:
            stmt = stmt.where(RuleWebhookDelivery.entity_id == entity_id)
        result = await self._db.execute(stmt)
        return [RuleWebhookDeliveryRead.model_validate(log) for log in result.scalars()]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch(self, app_id: uuid.UUID, rule_id: uuid.UUID) -> Rule:
        result = await self._db.execute(
            select(Rule).where(Rule.id == rule_id, Rule.app_id == app_id)
        )
        rule = result.scalar_one_or_none()
        if rule is None:
            raise RuleNotFoundError(str(rule_id))
        return rule

    async def _get_rules_raw(
        self,
        app_id: uuid.UUID,
        active_only: bool = True,
        entity_id: uuid.UUID | None = None,
    ) -> list[dict]:
        stmt = select(Rule).where(Rule.app_id == app_id)
        if active_only:
            stmt = stmt.where(Rule.is_active.is_(True))
        if entity_id:
            stmt = stmt.where(Rule.entity_id == entity_id)
        result = await self._db.execute(stmt)
        return [
            {
                "id": r.id,
                "entity_id": r.entity_id,
                "rule_type": r.rule_type,
                "trigger": r.trigger,
                "conditions": r.conditions,
                "actions": r.actions,
                "priority": r.priority,
            }
            for r in result.scalars()
        ]

    async def get_active_schedule_rules(self) -> list[dict]:
        """Every active rule with trigger.event='schedule', across all apps —
        used by the periodic sweep in app/worker/tasks/rules_schedule.py
        (ТЗ 3.5.1 "Расчёт"/"Уведомление": работа по расписанию, не по
        событию). Unlike _get_rules_raw this isn't scoped to one app,
        since the sweep has to look at everything in one pass."""
        stmt = select(Rule).where(
            Rule.is_active.is_(True),
            Rule.trigger["event"].astext == "schedule",
        )
        result = await self._db.execute(stmt)
        return [
            {
                "id": r.id,
                "app_id": r.app_id,
                "entity_id": r.entity_id,
                "trigger": r.trigger,
                "conditions": r.conditions,
                "actions": r.actions,
                "priority": r.priority,
            }
            for r in result.scalars()
        ]

    async def _assert_no_cycles(
        self, app_id: uuid.UUID, activating_rule_id: uuid.UUID
    ) -> None:
        """Raise RuleCycleError if activating this rule creates a cycle."""
        rules_raw = await self._get_rules_raw(app_id, active_only=False)
        # Mark the rule being activated as active for cycle check
        for r in rules_raw:
            if r["id"] == activating_rule_id:
                break

        graph = build_dependency_graph(extract_rule_nodes(rules_raw))
        cycles = find_cycles(graph)
        if cycles:
            raise RuleCycleError(cycles)
