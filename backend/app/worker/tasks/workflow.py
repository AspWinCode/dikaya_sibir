"""
Workflow Celery tasks.

check_sla_breach      — wakes up at the SLA deadline and, if the instance is
                        still in the expected state, fires the state's sla_breach_actions,
                        then schedules any configured escalation levels.

check_sla_escalation  — wakes up at sla_deadline + level.delay_seconds, reassigns
                        the instance to the level's assignee, and marks escalation_level.
"""

import uuid
from datetime import timedelta

import structlog
from celery import shared_task

from app.core.metrics import sla_breaches

logger = structlog.get_logger(__name__)


@shared_task(
    name="app.worker.tasks.workflow.check_sla_breach",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def check_sla_breach(
    self: object,
    instance_id: str,
    expected_state: str,
    workflow_id: str,
) -> dict:
    """
    Check whether a workflow instance has breached its SLA.

    If the instance is still in `expected_state` at execution time, run
    the state's `sla_breach_actions`. If the state has already changed,
    the transition happened in time — do nothing.
    After breach, schedule any escalation levels defined on the state.
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.engine.interpreter import ExecutionContext, execute_actions
        from app.models.workflow import StateDef, WorkflowInstance

        async with AsyncSessionLocal() as session:
            inst_result = await session.execute(
                select(WorkflowInstance).where(WorkflowInstance.id == uuid.UUID(instance_id))
            )
            instance = inst_result.scalar_one_or_none()
            if instance is None:
                logger.warning("sla_instance_not_found", instance_id=instance_id)
                return {"status": "skipped", "reason": "instance_not_found"}

            if instance.current_state != expected_state:
                logger.info(
                    "sla_state_changed",
                    instance_id=instance_id,
                    expected=expected_state,
                    actual=instance.current_state,
                )
                return {"status": "skipped", "reason": "state_already_changed"}

            state_result = await session.execute(
                select(StateDef).where(
                    StateDef.workflow_id == uuid.UUID(workflow_id),
                    StateDef.name == expected_state,
                )
            )
            state = state_result.scalar_one_or_none()
            if state is None:
                logger.info("sla_state_not_found", instance_id=instance_id, state=expected_state)
                return {"status": "skipped", "reason": "state_not_found"}

            if state.sla_breach_actions:
                ctx = ExecutionContext(
                    record={},
                    entity_id=instance.entity_id,
                    app_id=instance.app_id,
                    event="workflow.sla_breach",
                    extra={
                        "instance_id": instance_id,
                        "workflow_id": workflow_id,
                        "state": expected_state,
                    },
                )
                result = execute_actions(list(state.sla_breach_actions), ctx)

                for notif in result.notifications:
                    if notif.get("to"):
                        from app.worker.tasks.notifications import send_email

                        send_email.apply_async(
                            kwargs={
                                "to": notif["to"],
                                "subject": notif.get("subject", "SLA Breach"),
                                "body_html": notif.get("template", ""),
                            },
                            queue="notifications",
                        )

                sla_breaches.labels(workflow_id=workflow_id).inc()
                await session.commit()
                logger.info(
                    "sla_breach_executed",
                    instance_id=instance_id,
                    state=expected_state,
                    errors=result.errors,
                )

            # Schedule escalation levels
            sla_deadline = instance.sla_deadline
            for esc in state.escalation_levels or []:
                level_num = esc.get("level")
                delay = esc.get("delay_seconds")
                if level_num and delay is not None and sla_deadline is not None:
                    eta = sla_deadline + timedelta(seconds=int(delay))
                    check_sla_escalation.apply_async(
                        kwargs={
                            "instance_id": instance_id,
                            "expected_state": expected_state,
                            "workflow_id": workflow_id,
                            "escalation_level": level_num,
                        },
                        eta=eta,
                        queue="default",
                    )
                    logger.info(
                        "sla_escalation_scheduled",
                        instance_id=instance_id,
                        level=level_num,
                        delay_seconds=delay,
                    )

            return {
                "status": "executed",
                "instance_id": instance_id,
                "state": expected_state,
            }

    return asyncio.run(_run())


@shared_task(
    name="app.worker.tasks.workflow.check_sla_escalation",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    acks_late=True,
)
def check_sla_escalation(
    self: object,
    instance_id: str,
    expected_state: str,
    workflow_id: str,
    escalation_level: int,
) -> dict:
    """
    Reassign a workflow instance to the escalation level's assignee.

    Fires `delay_seconds` after sla_deadline. Skips if the instance has
    already moved to a different state or is already at a higher escalation level.
    """
    import asyncio

    async def _run() -> dict:
        from sqlalchemy import select, update

        from app.core.database import AsyncSessionLocal
        from app.models.workflow import StateDef, WorkflowInstance

        async with AsyncSessionLocal() as session:
            inst_result = await session.execute(
                select(WorkflowInstance).where(WorkflowInstance.id == uuid.UUID(instance_id))
            )
            instance = inst_result.scalar_one_or_none()
            if instance is None:
                logger.warning("esc_instance_not_found", instance_id=instance_id)
                return {"status": "skipped", "reason": "instance_not_found"}

            if instance.current_state != expected_state:
                return {"status": "skipped", "reason": "state_changed"}

            # Don't re-escalate if already at this level or higher
            if (
                instance.escalation_level is not None
                and instance.escalation_level >= escalation_level
            ):
                return {"status": "skipped", "reason": "already_escalated"}

            state_result = await session.execute(
                select(StateDef).where(
                    StateDef.workflow_id == uuid.UUID(workflow_id),
                    StateDef.name == expected_state,
                )
            )
            state = state_result.scalar_one_or_none()
            if state is None:
                return {"status": "skipped", "reason": "state_not_found"}

            esc_cfg = next(
                (e for e in (state.escalation_levels or []) if e.get("level") == escalation_level),
                None,
            )
            if esc_cfg is None:
                return {"status": "skipped", "reason": "escalation_level_not_configured"}

            assignee_type = esc_cfg.get("assignee_type")
            assignee_id_raw = esc_cfg.get("assignee_id")

            new_user_id: uuid.UUID | None = None
            new_group_id: uuid.UUID | None = None
            if assignee_type == "user" and assignee_id_raw:
                new_user_id = uuid.UUID(assignee_id_raw)
            elif assignee_type == "group" and assignee_id_raw:
                new_group_id = uuid.UUID(assignee_id_raw)

            await session.execute(
                update(WorkflowInstance)
                .where(
                    WorkflowInstance.id == uuid.UUID(instance_id),
                    WorkflowInstance.current_state == expected_state,
                )
                .values(
                    escalation_level=escalation_level,
                    assigned_user_id=new_user_id
                    if assignee_type == "user"
                    else instance.assigned_user_id,
                    assigned_group_id=new_group_id
                    if assignee_type == "group"
                    else instance.assigned_group_id,
                )
            )
            await session.commit()

            # Notify
            esc_cfg.get("message") or f"Эскалация уровня {escalation_level}"
            logger.info(
                "sla_escalation_executed",
                instance_id=instance_id,
                state=expected_state,
                level=escalation_level,
                assignee_type=assignee_type,
                assignee_id=assignee_id_raw,
            )
            return {
                "status": "executed",
                "instance_id": instance_id,
                "state": expected_state,
                "escalation_level": escalation_level,
            }

    return asyncio.run(_run())
