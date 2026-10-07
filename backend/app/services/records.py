"""RecordService: CRUD with JSONB payload, filter engine, cursor pagination, field validation."""

import base64
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Numeric

from app.core import field_crypto
from app.core.metrics import record_operations
from app.models.data import Record
from app.models.identity import AbacRule, User
from app.models.metamodel import Entity, Field, Relation
from app.schemas.common import CursorPage
from app.schemas.records import (
    FilterOp,
    ParsedFilter,
    RecordCreate,
    RecordListParams,
    RecordRead,
    RecordUpdate,
    TrashedRecordRead,
)
from app.services import abac

logger = structlog.get_logger(__name__)

MAX_PAYLOAD_KEYS = 200


class RecordNotFoundError(Exception):
    pass


class RecordValidationError(Exception):
    pass


def _cursor_encode(created_at: datetime, record_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{record_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _cursor_decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, uid = raw.split("|", 1)
    return datetime.fromisoformat(ts), uuid.UUID(uid)


# ------------------------------------------------------------------
# JSONB filter → SQLAlchemy expression
# ------------------------------------------------------------------


def _jsonb_text(field: str) -> Any:
    """payload->>'field' — text extraction."""
    return func.jsonb_extract_path_text(Record.payload, field)


def _build_condition(f: ParsedFilter) -> Any:
    """Convert a ParsedFilter into a SQLAlchemy WHERE clause."""
    text_expr = _jsonb_text(f.field)

    match f.op:
        case FilterOp.EQ:
            return text_expr == f.value
        case FilterOp.NE:
            return text_expr != f.value
        case FilterOp.GT:
            return cast(text_expr, Numeric) > float(f.value)  # type: ignore[arg-type]
        case FilterOp.GTE:
            return cast(text_expr, Numeric) >= float(f.value)  # type: ignore[arg-type]
        case FilterOp.LT:
            return cast(text_expr, Numeric) < float(f.value)  # type: ignore[arg-type]
        case FilterOp.LTE:
            return cast(text_expr, Numeric) <= float(f.value)  # type: ignore[arg-type]
        case FilterOp.CONTAINS:
            return text_expr.contains(f.value)
        case FilterOp.ICONTAINS:
            return text_expr.ilike(f"%{f.value}%")
        case FilterOp.IN:
            values = [v.strip() for v in (f.value or "").split(",")]
            return text_expr.in_(values)
        case FilterOp.NIN:
            values = [v.strip() for v in (f.value or "").split(",")]
            return text_expr.notin_(values)
        case FilterOp.IS_NULL:
            # field is absent from JSON or explicitly null
            return or_(
                text_expr.is_(None),
                ~Record.payload.has_key(f.field),
            )
        case FilterOp.IS_NOT_NULL:
            return and_(
                text_expr.isnot(None),
                Record.payload.has_key(f.field),
            )
        case _:
            raise ValueError(f"Unsupported filter op: {f.op}")


# ------------------------------------------------------------------
# Field validation
# ------------------------------------------------------------------


def _validate_payload(
    payload: dict[str, Any],
    fields: list[Field],
    partial: bool = False,
) -> None:
    """
    Validate record payload against entity field definitions.
    partial=True skips required-field check (used for PATCH).
    """
    if len(payload) > MAX_PAYLOAD_KEYS:
        raise RecordValidationError(f"Payload exceeds {MAX_PAYLOAD_KEYS} keys")

    field_map = {f.name: f for f in fields if not f.is_system}

    # Check for unknown fields
    unknown = set(payload) - set(field_map)
    # Allow _id/_meta style internal keys to pass through
    unknown = {k for k in unknown if not k.startswith("_")}
    if unknown:
        raise RecordValidationError(f"Unknown fields: {sorted(unknown)}")

    if not partial:
        # Check required fields
        missing = [f.name for f in field_map.values() if f.is_required and f.name not in payload]
        if missing:
            raise RecordValidationError(f"Required fields missing: {missing}")

    # Type-level validation
    for name, value in payload.items():
        field = field_map.get(name)
        if not field:
            continue
        _validate_field_value(field, name, value)

    # Conditional-required validation (validation_rules.extra_conditions).
    # Only enforced when every referenced field is present in this payload —
    # a partial PATCH that doesn't touch those fields is left unevaluated.
    for field in field_map.values():
        rules = field.validation_rules or {}
        conds_raw = rules.get("extra_conditions") or []
        if not conds_raw or not _conditions_met(conds_raw, payload):
            continue
        if field.name not in payload or payload.get(field.name) is None:
            msg = rules.get("custom_message") or (
                f"Field '{field.name}' is required because its conditions are met"
            )
            raise RecordValidationError(msg)


def _conditions_met(conds_raw: list[Any], payload: dict[str, Any]) -> bool:
    """True only if every condition is present in payload and holds."""
    conditions = []
    for raw in conds_raw:
        try:
            cond = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            return False
        conditions.append(cond)

    if not conditions:
        return False

    for cond in conditions:
        field_name = cond.get("field")
        if field_name is None or field_name not in payload:
            return False
        if not _eval_compare(payload.get(field_name), cond.get("op"), cond.get("value")):
            return False
    return True


def _eval_compare(actual: Any, op: str | None, expected: Any) -> bool:
    if op == "is_null":
        return actual is None
    if op == "is_not_null":
        return actual is not None
    if actual is None:
        return False
    if op == "contains":
        return str(expected) in str(actual)
    try:
        a, b = float(actual), float(expected)
        return {
            "eq": a == b,
            "ne": a != b,
            "gt": a > b,
            "gte": a >= b,
            "lt": a < b,
            "lte": a <= b,
        }.get(op or "", False)
    except (TypeError, ValueError):
        pass
    s_actual = str(actual)
    s_expected = str(expected)
    if op == "eq":
        return s_actual == s_expected
    if op == "ne":
        return s_actual != s_expected
    return False


def _parse_date_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise ValueError("not a date")


def _choice_values(raw_choices: Any) -> list[Any]:
    """Extract the selectable values from a field's `field_options.choices`.

    Two shapes exist in the wild: entities created through the entity builder
    store choices as bare strings (`["draft", "paid"]`), while module-installed
    entities store `{"value": ..., "label": ...}` objects. Accept both so
    validation doesn't crash on whichever shape a given field actually has.
    """
    if not isinstance(raw_choices, list):
        return []
    return [c["value"] if isinstance(c, dict) else c for c in raw_choices]


def _validate_field_value(field: Field, name: str, value: Any) -> None:
    rules = field.validation_rules or {}
    try:
        _check_field_value(field, name, value, rules)
    except RecordValidationError:
        custom_message = rules.get("custom_message")
        if custom_message:
            raise RecordValidationError(custom_message) from None
        raise


def _check_field_value(field: Field, name: str, value: Any, rules: dict) -> None:
    ft = field.field_type
    opts = field.field_options or {}

    if value is None:
        if field.is_required:
            raise RecordValidationError(f"Field '{name}' is required, got null")
        return

    if ft in ("text", "long_text", "rich_text", "url", "email", "phone"):
        if not isinstance(value, str):
            raise RecordValidationError(
                f"Field '{name}' expects string, got {type(value).__name__}"
            )
        if "min_length" in rules and len(value) < rules["min_length"]:
            raise RecordValidationError(f"Field '{name}' below min_length {rules['min_length']}")
        if "max_length" in rules and len(value) > rules["max_length"]:
            raise RecordValidationError(f"Field '{name}' exceeds max_length {rules['max_length']}")
        if "pattern" in rules:
            try:
                ok = re.fullmatch(rules["pattern"], value) is not None
            except re.error:
                ok = True  # a broken stored regex shouldn't block every write
            if not ok:
                raise RecordValidationError(
                    rules.get("pattern_message")
                    or f"Field '{name}' does not match required pattern"
                )
        if ft == "email" and "@" not in value:
            raise RecordValidationError(f"Field '{name}' is not a valid email")

    elif ft in ("number", "decimal", "currency"):
        if not isinstance(value, int | float):
            try:
                float(value)
            except (TypeError, ValueError) as exc:
                raise RecordValidationError(f"Field '{name}' expects number") from exc
        if "min" in rules and float(value) < rules["min"]:
            raise RecordValidationError(f"Field '{name}' below minimum {rules['min']}")
        if "max" in rules and float(value) > rules["max"]:
            raise RecordValidationError(f"Field '{name}' above maximum {rules['max']}")

    elif ft == "boolean":
        if not isinstance(value, bool):
            raise RecordValidationError(f"Field '{name}' expects boolean")

    elif ft in ("date", "datetime"):
        try:
            dt = _parse_date_value(value)
        except (TypeError, ValueError) as exc:
            raise RecordValidationError(
                f"Field '{name}' expects an ISO date/datetime string"
            ) from exc
        if "min_date" in rules and dt < _parse_date_value(rules["min_date"]):
            raise RecordValidationError(
                f"Field '{name}' is before minimum date {rules['min_date']}"
            )
        if "max_date" in rules and dt > _parse_date_value(rules["max_date"]):
            raise RecordValidationError(f"Field '{name}' is after maximum date {rules['max_date']}")
        if rules.get("future_only") and dt <= datetime.now(UTC):
            raise RecordValidationError(f"Field '{name}' must be a future date")
        if rules.get("past_only") and dt >= datetime.now(UTC):
            raise RecordValidationError(f"Field '{name}' must be a past date")

    elif ft == "select":
        choices = _choice_values(opts.get("choices", []))
        if choices and value not in choices:
            raise RecordValidationError(f"Field '{name}': {value!r} not in choices {choices}")
        allowed = rules.get("allowed_values")
        if allowed and value not in allowed:
            raise RecordValidationError(
                f"Field '{name}': {value!r} not in allowed values {allowed}"
            )

    elif ft == "autonumber":
        # Auto-filled by SequenceService — never sent by the user; skip validation
        return

    elif ft == "multi_select":
        if not isinstance(value, list):
            raise RecordValidationError(f"Field '{name}' expects list for multi_select")
        choices = _choice_values(opts.get("choices", []))
        if choices:
            invalid = [v for v in value if v not in choices]
            if invalid:
                raise RecordValidationError(f"Field '{name}': invalid choices {invalid}")
        allowed = rules.get("allowed_values")
        if allowed:
            invalid = [v for v in value if v not in allowed]
            if invalid:
                raise RecordValidationError(f"Field '{name}': values not allowed {invalid}")
        if "min_selected" in rules and len(value) < rules["min_selected"]:
            raise RecordValidationError(
                f"Field '{name}' requires at least {rules['min_selected']} selected"
            )
        if "max_selected" in rules and len(value) > rules["max_selected"]:
            raise RecordValidationError(
                f"Field '{name}' allows at most {rules['max_selected']} selected"
            )


# ------------------------------------------------------------------
# Formula evaluation
# ------------------------------------------------------------------


def _evaluate_formulas(payload: dict[str, Any], fields: list[Field]) -> dict[str, Any]:
    """Compute formula fields and inject their values into the payload."""
    from app.engine.expressions import ExpressionError, evaluate

    formula_fields = [f for f in fields if f.field_type == "formula" and f.formula_definition]
    if not formula_fields:
        return payload

    result = dict(payload)
    for field in formula_fields:
        ast = (
            field.formula_definition.get("ast")
            if isinstance(field.formula_definition, dict)
            else field.formula_definition
        )
        if ast is None:
            ast = field.formula_definition
        if not isinstance(ast, dict):
            continue
        try:
            value = evaluate(ast, result)
            result[field.name] = value
        except (ExpressionError, Exception) as exc:
            logger.warning("formula_eval_failed", field=field.name, error=str(exc))
    return result


# ------------------------------------------------------------------
# Row-level ABAC (AbacRule) — condition grammar and SQL building live in
# app.services.abac, shared with rule validation in app.services.roles.
# ------------------------------------------------------------------


async def _apply_abac_row_scope(
    db: AsyncSession,
    stmt: Any,
    entity_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    actor_roles: list[str] | None,
) -> Any:
    return await abac.apply_row_scope(
        db,
        stmt,
        entity_id,
        actor_id,
        actor_roles,
        record_model=Record,
        abac_rule_model=AbacRule,
        user_model=User,
    )


# ------------------------------------------------------------------
# RecordService
# ------------------------------------------------------------------


class RecordService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _sensitive_names(fields: list[Field]) -> set[str]:
        return {f.name for f in fields if f.is_sensitive}

    async def get_sensitive_field_names(self, entity_id: uuid.UUID) -> set[str]:
        """Public helper for callers outside RecordService (e.g. the API
        layer building audit-log entries) that need to mask a payload
        without going through the encrypt/decrypt round trip."""
        return self._sensitive_names(await self._get_entity_fields(entity_id))

    async def list_records(
        self,
        entity_id: uuid.UUID,
        params: RecordListParams,
        actor_id: uuid.UUID | None = None,
        actor_roles: list[str] | None = None,
    ) -> CursorPage[RecordRead]:
        fields = await self._get_entity_fields(entity_id)
        sensitive_names = self._sensitive_names(fields)
        if sensitive_names:
            if params.sort_field in sensitive_names:
                raise RecordValidationError(
                    f"Cannot sort by encrypted field: {params.sort_field!r}"
                )
            bad_filters = [f.field for f in params.filters if f.field in sensitive_names]
            if bad_filters:
                raise RecordValidationError(f"Cannot filter by encrypted field(s): {bad_filters}")

        stmt = (
            select(Record)
            .where(Record.entity_id == entity_id)
            .order_by(Record.created_at.asc(), Record.id.asc())
        )

        if not params.include_deleted:
            stmt = stmt.where(Record.is_deleted.is_(False))

        stmt = await _apply_abac_row_scope(self._db, stmt, entity_id, actor_id, actor_roles)

        # JSONB filters
        for f in params.filters:
            stmt = stmt.where(_build_condition(f))

        # Custom sort by payload field
        if params.sort_field:
            sort_expr = _jsonb_text(params.sort_field)
            stmt = stmt.order_by(sort_expr.asc() if params.sort_dir == "asc" else sort_expr.desc())

        # Cursor pagination
        if params.cursor:
            cur_ts, cur_id = _cursor_decode(params.cursor)
            stmt = stmt.where(
                or_(
                    Record.created_at > cur_ts,
                    and_(Record.created_at == cur_ts, Record.id > cur_id),
                )
            )

        stmt = stmt.limit(params.limit + 1)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        has_more = len(rows) > params.limit
        items = rows[: params.limit]
        next_cursor = _cursor_encode(items[-1].created_at, items[-1].id) if has_more else None
        record_operations.labels(operation="list").inc()
        reads = [RecordRead.model_validate(r) for r in items]
        if sensitive_names:
            reads = [
                r.model_copy(
                    update={
                        "payload": field_crypto.decrypt_sensitive_fields(r.payload, sensitive_names)
                    }
                )
                for r in reads
            ]
        return CursorPage(items=reads, next_cursor=next_cursor, has_more=has_more)

    async def _assert_row_visible(
        self,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        actor_roles: list[str] | None,
    ) -> None:
        """Raise RecordNotFoundError if row-level ABAC hides this record from
        the caller. Used to gate reads *and* writes — a "deny" ABAC rule
        means the record can't be edited or deleted either, not just hidden
        from lists (ТЗ 3.1.4: "видимость и редактируемость")."""
        if not actor_roles:
            return
        stmt = await _apply_abac_row_scope(
            self._db,
            select(Record.id).where(Record.id == record_id),
            entity_id,
            actor_id,
            actor_roles,
        )
        visible = (await self._db.execute(stmt)).scalar_one_or_none()
        if visible is None:
            raise RecordNotFoundError(f"Record {record_id} not found")

    async def get_record(
        self,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        actor_roles: list[str] | None = None,
    ) -> RecordRead:
        record = await self._fetch(entity_id, record_id)
        await self._assert_row_visible(entity_id, record_id, actor_id, actor_roles)
        record_operations.labels(operation="read").inc()
        read = RecordRead.model_validate(record)
        sensitive_names = await self.get_sensitive_field_names(entity_id)
        if sensitive_names:
            read = read.model_copy(
                update={
                    "payload": field_crypto.decrypt_sensitive_fields(read.payload, sensitive_names)
                }
            )
        return read

    async def create_record(
        self,
        entity_id: uuid.UUID,
        data: RecordCreate,
        app_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> RecordRead:
        from app.services.sequences import SequenceService  # local import avoids circular
        from app.services.validation_rules import ValidationRuleService

        fields = await self._get_entity_fields(entity_id)
        # Fill autonumber fields before validation so they don't fail required-check
        payload = await SequenceService(self._db).fill_autonumber_fields(
            entity_id, data.payload, fields
        )
        _validate_payload(payload, fields, partial=False)
        payload = _evaluate_formulas(payload, fields)

        # Synchronous, pre-commit validation rules (rule_type="validation")
        # get first look — nothing has been written yet, so a block_save
        # raises cleanly with no rollback needed. Unlike automation rules
        # (async, post-commit — see RuleService.evaluate_rules_for_event).
        await ValidationRuleService(self._db).run(
            app_id,
            entity_id,
            "record.created",
            payload,
            actor_id=actor_id,
        )

        sensitive_names = self._sensitive_names(fields)
        record = Record(
            entity_id=entity_id,
            payload=field_crypto.encrypt_sensitive_fields(payload, sensitive_names),
            created_by=actor_id,
            updated_by=actor_id,
        )
        self._db.add(record)
        await self._db.flush()
        record_operations.labels(operation="create").inc()
        logger.info("record_created", record_id=str(record.id), entity_id=str(entity_id))
        read = RecordRead.model_validate(record)
        return read.model_copy(update={"payload": payload}) if sensitive_names else read

    async def update_record(
        self,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        data: RecordUpdate,
        app_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
        actor_roles: list[str] | None = None,
    ) -> RecordRead:
        from app.services.validation_rules import ValidationRuleService

        record = await self._fetch(entity_id, record_id)
        await self._assert_row_visible(entity_id, record_id, actor_id, actor_roles)
        fields = await self._get_entity_fields(entity_id)
        _validate_payload(data.payload, fields, partial=True)

        sensitive_names = self._sensitive_names(fields)
        existing_payload = field_crypto.decrypt_sensitive_fields(record.payload, sensitive_names)

        # JSONB merge: existing (decrypted) payload + incoming updates
        merged = {**existing_payload, **data.payload}
        # Remove keys explicitly set to None (delete semantics)
        merged = {k: v for k, v in merged.items() if v is not None}
        merged = _evaluate_formulas(merged, fields)

        await ValidationRuleService(self._db).run(
            app_id,
            entity_id,
            "record.updated",
            merged,
            record_id=record_id,
            changed_fields=list(data.payload.keys()),
            actor_id=actor_id,
        )

        await self._db.execute(
            update(Record)
            .where(Record.entity_id == entity_id, Record.id == record_id)
            .values(
                payload=field_crypto.encrypt_sensitive_fields(merged, sensitive_names),
                version=Record.version + 1,
                updated_by=actor_id,
                updated_at=datetime.now(UTC),
            )
        )
        await self._db.flush()
        record_operations.labels(operation="update").inc()
        return await self.get_record(entity_id, record_id)

    async def delete_record(
        self,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        hard: bool = False,
        actor_id: uuid.UUID | None = None,
        actor_roles: list[str] | None = None,
        _seen: set[tuple[uuid.UUID, uuid.UUID]] | None = None,
    ) -> None:
        seen = _seen if _seen is not None else set()
        key = (entity_id, record_id)
        if key in seen:
            return
        seen.add(key)

        # Row-level ABAC is only enforced against the record the caller
        # explicitly targeted, not cascade-deleted descendants (those are
        # a side effect of deleting a record the caller was already allowed
        # to touch, not an independent user action).
        if _seen is None:
            await self._assert_row_visible(entity_id, record_id, actor_id, actor_roles)

        record = await self._fetch(entity_id, record_id)

        if not hard:
            await self._cascade_soft_delete(entity_id, record_id, actor_id, seen)

        if hard:
            await self._db.delete(record)
        else:
            record.is_deleted = True
            record.deleted_at = datetime.now(UTC)
            record.deleted_by = actor_id
        await self._db.flush()
        record_operations.labels(operation="delete").inc()
        logger.info("record_deleted", record_id=str(record_id), hard=hard)

    async def restore_record(self, entity_id: uuid.UUID, record_id: uuid.UUID) -> RecordRead:
        stmt = select(Record).where(
            Record.entity_id == entity_id,
            Record.id == record_id,
            Record.is_deleted.is_(True),
        )
        result = await self._db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise RecordNotFoundError(str(record_id))
        record.is_deleted = False
        record.deleted_at = None
        record.deleted_by = None
        await self._db.flush()

        await self._cascade_restore(entity_id, record_id)

        await self._db.refresh(record, attribute_names=["updated_at"])
        read = RecordRead.model_validate(record)
        sensitive_names = await self.get_sensitive_field_names(entity_id)
        if sensitive_names:
            read = read.model_copy(
                update={
                    "payload": field_crypto.decrypt_sensitive_fields(read.payload, sensitive_names)
                }
            )
        return read

    async def list_deleted_records(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CursorPage[TrashedRecordRead]:
        """App-wide «Корзина» (ТЗ 3.9.1): every soft-deleted record across the
        app's entities (or just one, if `entity_id` is given), most recently
        deleted first."""
        entities_stmt = select(Entity).where(Entity.app_id == app_id)
        if entity_id:
            entities_stmt = entities_stmt.where(Entity.id == entity_id)
        entities_by_id = {e.id: e for e in (await self._db.execute(entities_stmt)).scalars().all()}
        if not entities_by_id:
            return CursorPage(items=[], next_cursor=None, has_more=False, total=0)

        stmt = (
            select(Record)
            .where(Record.entity_id.in_(entities_by_id.keys()), Record.is_deleted.is_(True))
            .order_by(Record.deleted_at.desc().nulls_last(), Record.id.desc())
        )
        if cursor:
            cur_ts, cur_id = _cursor_decode(cursor)
            stmt = stmt.where(
                or_(
                    Record.deleted_at < cur_ts,
                    and_(Record.deleted_at == cur_ts, Record.id < cur_id),
                )
            )
        stmt = stmt.limit(limit + 1)
        rows = (await self._db.execute(stmt)).scalars().all()

        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = (
            _cursor_encode(items[-1].deleted_at, items[-1].id)
            if has_more and items[-1].deleted_at is not None
            else None
        )

        trashed = [
            TrashedRecordRead(
                id=r.id,
                entity_id=r.entity_id,
                entity_slug=entities_by_id[r.entity_id].slug,
                entity_display_name=entities_by_id[r.entity_id].display_name,
                payload=r.payload,
                is_cascade_deleted=r.cascade_deleted_by is not None,
                deleted_at=r.deleted_at,
                deleted_by=r.deleted_by,
            )
            for r in items
        ]
        return CursorPage(items=trashed, next_cursor=next_cursor, has_more=has_more)

    # ------------------------------------------------------------------
    # Cascade helpers

    async def _cascade_soft_delete(
        self,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        seen: set[tuple[uuid.UUID, uuid.UUID]],
    ) -> None:
        """Soft-delete dependents: records in other entities whose relation field
        points at this record (excluding MANY_TO_MANY).

        Deliberately one-directional: a record's own outgoing relation fields
        point at records it merely references (e.g. a shared catalog entry),
        not records it owns. Cascading in that direction would soft-delete
        unrelated rows still referenced elsewhere (see incident: deleting a
        "Детали отчёта" row cascaded into soft-deleting the referenced
        "Операция"/"Раздел предприятия" catalog records).
        """
        cascade_types = ("one_to_one", "one_to_many")

        in_rels = (
            (
                await self._db.execute(
                    select(Relation).where(
                        Relation.to_entity_id == entity_id,
                        Relation.relation_type.in_(cascade_types),
                    )
                )
            )
            .scalars()
            .all()
        )

        for rel in in_rels:
            field = rel.from_field_name
            children = (
                (
                    await self._db.execute(
                        select(Record).where(
                            Record.entity_id == rel.from_entity_id,
                            Record.is_deleted.is_(False),
                            or_(
                                Record.payload[field].astext == str(record_id),
                                cast(Record.payload[field], JSONB).contains([str(record_id)]),
                            ),
                        )
                    )
                )
                .scalars()
                .all()
            )

            for child in children:
                await self._soft_delete_child(
                    rel.from_entity_id, child.id, record_id, actor_id, seen
                )

    async def _soft_delete_child(
        self,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        parent_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        seen: set[tuple[uuid.UUID, uuid.UUID]],
    ) -> None:
        key = (entity_id, record_id)
        if key in seen:
            return
        seen.add(key)

        # Recurse first so grandchildren are deleted before the child
        await self._cascade_soft_delete(entity_id, record_id, actor_id, seen)

        await self._db.execute(
            update(Record)
            .where(
                Record.entity_id == entity_id,
                Record.id == record_id,
                Record.is_deleted.is_(False),
            )
            .values(
                is_deleted=True,
                cascade_deleted_by=parent_id,
                deleted_at=datetime.now(UTC),
                deleted_by=actor_id,
            )
        )

    async def _cascade_restore(self, entity_id: uuid.UUID, record_id: uuid.UUID) -> None:
        """Restore all records that were cascade-deleted because of this record."""
        # Find direct children that were cascade-deleted by this record
        children = (
            (
                await self._db.execute(
                    select(Record).where(
                        Record.cascade_deleted_by == record_id,
                        Record.is_deleted.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )

        for child in children:
            await self._cascade_restore(child.entity_id, child.id)
            await self._db.execute(
                update(Record)
                .where(
                    Record.entity_id == child.entity_id,
                    Record.id == child.id,
                )
                .values(is_deleted=False, cascade_deleted_by=None, deleted_at=None, deleted_by=None)
            )

    # ------------------------------------------------------------------
    async def _fetch(self, entity_id: uuid.UUID, record_id: uuid.UUID) -> Record:
        stmt = select(Record).where(
            Record.entity_id == entity_id,
            Record.id == record_id,
            Record.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        record = result.scalar_one_or_none()
        if record is None:
            raise RecordNotFoundError(str(record_id))
        return record

    async def _get_entity_fields(self, entity_id: uuid.UUID) -> list[Field]:
        result = await self._db.execute(select(Field).where(Field.entity_id == entity_id))
        return list(result.scalars())
