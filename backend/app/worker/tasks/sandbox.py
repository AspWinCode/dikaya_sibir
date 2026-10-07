"""
Sandbox Celery worker — executes Rules Engine tasks.
This worker runs in an isolated queue (no external network access in prod).
Hard time limit: 120s / soft: 113s (Celery enforced) — applies to the WHOLE
batch of rules matching one record event, not per rule. All active rules for
one event are evaluated together (not as independent tasks) so that
priority-based conflict resolution (ТЗ 3.5.4) is actually deterministic —
see app.engine.interpreter.run_rules_batch and app.services.rules.RuleService
.evaluate_rules_for_event for why per-rule tasks couldn't guarantee that.
"""

import time
import uuid

import structlog
from celery import shared_task

from app.core.metrics import rule_executions
from app.engine.interpreter import BatchResult, ExecutionContext, RuleOutcome, run_rules_batch

logger = structlog.get_logger(__name__)


@shared_task(
    name="app.worker.tasks.sandbox.execute_rules_batch",
    bind=True,
    max_retries=0,  # Rules must not auto-retry — side effects may have occurred
    time_limit=120,
    soft_time_limit=113,
    acks_late=True,
)
def execute_rules_batch(
    self: object,
    rules: list[dict],
    context: dict,
    execution_batch_id: str,
) -> dict:
    """
    Evaluate every active rule matching one record event together, in
    priority order (`rules` must already be sorted ascending by priority —
    RuleService does this before dispatch), and persist the outcome:
      - one merged set of field mutations, conflicts resolved by priority
      - every matched rule's create/update/delete/notification/webhook actions
      - one RuleExecutionLog row per rule (always written, best-effort)
      - one RuleConflictLog row per field that had a priority conflict
    """
    start = time.monotonic()
    ctx = ExecutionContext(
        record=dict(context.get("record", {})),
        entity_id=uuid.UUID(context["entity_id"]),
        app_id=uuid.UUID(context["app_id"]),
        event=context.get("event", "record.updated"),
        actor_id=uuid.UUID(context["actor_id"]) if context.get("actor_id") else None,
        record_id=uuid.UUID(context["record_id"]) if context.get("record_id") else None,
        changed_fields=context.get("changed_fields", []),
    )

    batch = run_rules_batch(rules, ctx)

    persist_error: str | None = None
    try:
        _persist_batch(batch, ctx, execution_batch_id)
    except Exception as exc:
        persist_error = str(exc)
        logger.exception(
            "rule_batch_persist_error", execution_batch_id=execution_batch_id, error=persist_error
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    _write_execution_logs(batch, ctx, persist_error, duration_ms, execution_batch_id)

    for outcome in batch.outcomes:
        status = _rule_status(outcome, persist_error)
        rule_executions.labels(status=status).inc()

    logger.info(
        "rule_batch_executed",
        execution_batch_id=execution_batch_id,
        rule_count=len(rules),
        conflict_count=len(batch.conflicts),
        duration_ms=duration_ms,
        failed=bool(persist_error),
    )
    return {
        "status": "failed" if persist_error else "success",
        "execution_batch_id": execution_batch_id,
        "duration_ms": duration_ms,
        "conflicts": len(batch.conflicts),
        "error": persist_error,
    }


def _rule_status(outcome: RuleOutcome, persist_error: str | None) -> str:
    if persist_error:
        return "failed"
    if not outcome.result.matched:
        return "skipped"
    return "failed" if outcome.result.errors else "success"


def _persist_batch(batch: BatchResult, ctx: ExecutionContext, execution_batch_id: str) -> None:
    """Apply the batch's merged mutations, record operations, and conflict
    log entries in one atomic transaction.

    Uses its own freshly-created, unpooled engine rather than the app-wide
    `app.core.database.engine` singleton. This function runs inside
    `asyncio.run()` (see the bottom of this function) — a brand new event
    loop on every call, since the Celery task calling it is synchronous
    and has no loop of its own between invocations. asyncpg connections
    are not safe to reuse across event loops; reusing the shared engine's
    pooled connections here reproducibly fails on the second call in a
    worker process's lifetime with "cannot perform operation: another
    operation is in progress" / "attached to a different loop" (confirmed
    end to end against a real worker while building ТЗ item 13's balance
    rule). NullPool means every connection this engine hands out is closed
    immediately on release rather than pooled for reuse — the small
    reconnect cost per call is negligible next to the 113s sandbox budget,
    and correctness here matters far more than connection-reuse overhead.
    """
    import asyncio

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.data import Record
    from app.models.logic import RuleConflictLog

    db_url = str(settings.DATABASE_URL).replace("postgresql://", "postgresql+asyncpg://", 1)

    async def _run() -> None:
        run_engine = create_async_engine(db_url, poolclass=NullPool)
        run_session_factory = async_sessionmaker(
            bind=run_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        async with run_session_factory() as session:
            if batch.applied_mutations and ctx.record_id:
                stmt = select(Record).where(
                    Record.entity_id == ctx.entity_id,
                    Record.id == ctx.record_id,
                    Record.is_deleted.is_(False),
                )
                res = await session.execute(stmt)
                record = res.scalar_one_or_none()
                if record:
                    record.payload = {**record.payload, **batch.applied_mutations}
                    record.version += 1

            for rec_create in batch.records_to_create:
                entity_id_str = rec_create.get("entity_id")
                target_entity = uuid.UUID(entity_id_str) if entity_id_str else ctx.entity_id
                match = rec_create.get("match")
                if match:
                    # Upsert: `match` narrows to the record(s) this logically
                    # is (e.g. {product_field: X, location_field: Y} for a
                    # running-balance table) — exact-equality JSONB lookup,
                    # same pattern already used in records.py. On a hit, add
                    # `increment` deltas to the existing numeric fields
                    # instead of creating a duplicate row; on a miss, create
                    # one seeded with `payload`.
                    stmt = select(Record).where(
                        Record.entity_id == target_entity,
                        Record.is_deleted.is_(False),
                        *[Record.payload[k].astext == str(v) for k, v in match.items()],
                    )
                    existing = (await session.execute(stmt)).scalars().first()
                    if existing:
                        increment = rec_create.get("increment") or {}
                        new_payload = dict(existing.payload)
                        for k, delta in increment.items():
                            # Record payloads store numeric field values as
                            # JSON strings (whatever a form input's text
                            # sent), not JSON numbers — confirmed on prod
                            # data, not an assumption. `delta` is a float
                            # from expression evaluation, so adding it to
                            # the raw string blew up with "can only
                            # concatenate str (not 'float') to str" the
                            # first time an upsert actually hit an existing
                            # row (ТЗ item 13's second balance-affecting
                            # write onto the same product+location).
                            current_raw = new_payload.get(k)
                            current_num = (
                                0.0
                                if current_raw is None or current_raw == ""
                                else float(current_raw)
                            )
                            result = current_num + float(delta)
                            new_payload[k] = (
                                str(int(result)) if result == int(result) else str(result)
                            )
                        existing.payload = new_payload
                        existing.updated_by = ctx.actor_id
                        existing.version += 1
                        continue
                session.add(
                    Record(
                        entity_id=target_entity,
                        payload=rec_create.get("payload", {}),
                        created_by=ctx.actor_id,
                        updated_by=ctx.actor_id,
                    )
                )

            for rec_update in batch.records_to_update:
                try:
                    target_id = uuid.UUID(rec_update["record_id"])
                except (KeyError, ValueError):
                    continue
                stmt = select(Record).where(Record.id == target_id, Record.is_deleted.is_(False))
                res = await session.execute(stmt)
                record = res.scalar_one_or_none()
                if record:
                    record.payload = {**record.payload, **rec_update.get("payload", {})}
                    record.version += 1

            for record_id_str in batch.records_to_delete:
                try:
                    target_id = uuid.UUID(record_id_str)
                except ValueError:
                    continue
                stmt = select(Record).where(Record.id == target_id, Record.is_deleted.is_(False))
                res = await session.execute(stmt)
                record = res.scalar_one_or_none()
                if record:
                    record.is_deleted = True

            for conflict in batch.conflicts:
                session.add(
                    RuleConflictLog(
                        app_id=ctx.app_id,
                        entity_id=ctx.entity_id,
                        record_id=ctx.record_id,
                        event=ctx.event,
                        field_name=conflict.field_name,
                        winning_rule_id=uuid.UUID(conflict.winning_rule_id),
                        winning_value=conflict.winning_value,
                        losing_writes=conflict.losing_writes,
                        execution_batch_id=uuid.UUID(execution_batch_id),
                    )
                )

            for notif in batch.notifications:
                if not notif.get("to"):
                    continue
                from app.worker.tasks.notifications import send_email

                template_str = notif.get("template", "")
                record_ctx = notif.get("context", {})
                try:
                    from jinja2 import BaseLoader, Environment, select_autoescape

                    env = Environment(loader=BaseLoader(), autoescape=select_autoescape(["html"]))
                    body_html = env.from_string(template_str).render(**record_ctx)
                except Exception:
                    body_html = template_str
                send_email.apply_async(
                    kwargs={
                        "to": notif["to"],
                        "subject": notif.get("subject", ""),
                        "body_html": body_html,
                    },
                    queue="notifications",
                )

            for webhook in batch.webhooks:
                url = webhook.get("url")
                if not url:
                    continue
                from app.worker.tasks.notifications import deliver_rule_webhook

                deliver_rule_webhook.apply_async(
                    kwargs={
                        "app_id": str(ctx.app_id),
                        "entity_id": str(ctx.entity_id),
                        "record_id": str(ctx.record_id) if ctx.record_id else None,
                        "execution_batch_id": execution_batch_id,
                        "url": url,
                        "method": webhook.get("method", "POST"),
                        "payload": webhook.get("payload", {}),
                    },
                    queue="notifications",
                )

            await session.commit()
        await run_engine.dispose()

    asyncio.run(_run())


def _write_execution_logs(
    batch: BatchResult,
    ctx: ExecutionContext,
    persist_error: str | None,
    duration_ms: int,
    execution_batch_id: str,
) -> None:
    """Write one RuleExecutionLog row per rule (best-effort, non-blocking —
    mirrors the old per-rule task's behavior of always leaving an audit
    trail even when persistence itself failed). Uses its own NullPool
    engine for the same reason _persist_batch does — the shared
    app.core.database engine's pooled asyncpg connections aren't safe to
    reuse across the fresh event loop asyncio.run() creates on every call
    (see _persist_batch's docstring). Confirmed on prod: before this fix,
    every RuleExecutionLog write here failed silently with "attached to a
    different loop" on the second call in a worker process's lifetime,
    so the table stayed empty regardless of whether rules actually ran."""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.logic import RuleExecutionLog

    db_url = str(settings.DATABASE_URL).replace("postgresql://", "postgresql+asyncpg://", 1)

    async def _run() -> None:
        run_engine = create_async_engine(db_url, poolclass=NullPool)
        run_session_factory = async_sessionmaker(
            bind=run_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        async with run_session_factory() as session:
            for outcome in batch.outcomes:
                status = _rule_status(outcome, persist_error)
                output = None
                if outcome.result.matched:
                    output = {
                        "field_mutations": outcome.result.field_mutations,
                        "overridden_fields": outcome.overridden_fields,
                        "records_to_create": outcome.result.records_to_create,
                        "records_to_update": outcome.result.records_to_update,
                        "records_to_delete": outcome.result.records_to_delete,
                        "notifications": outcome.result.notifications,
                        "webhooks": outcome.result.webhooks,
                        "errors": outcome.result.errors,
                    }
                session.add(
                    RuleExecutionLog(
                        rule_id=uuid.UUID(outcome.rule_id),
                        record_id=ctx.record_id,
                        entity_id=ctx.entity_id,
                        app_id=ctx.app_id,
                        event=ctx.event,
                        status=status,
                        duration_ms=duration_ms,
                        error=persist_error or ("; ".join(outcome.result.errors) or None),
                        input_snapshot=ctx.record,
                        output_snapshot=output,
                    )
                )
            await session.commit()
        await run_engine.dispose()

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.warning(
            "rule_batch_log_write_failed", execution_batch_id=execution_batch_id, error=str(exc)
        )
