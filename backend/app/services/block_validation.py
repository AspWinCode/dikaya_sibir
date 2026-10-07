"""Backend-side validation for page block configs, at the persistence
boundary (UIService.create_page/update_page) — the frontend already guides
the user through Источник → Показатель → Расчёт → Группировка → Фильтр and
blocks obviously-invalid combinations in its own UI, but a client that
posts directly to the API must not be able to save a config the runtime
can't actually execute (ТЗ item 4).

Only the "pivot" block type is covered — that's the one report/aggregation
block type with real runtime semantics (entity + fields + aggregation);
other block types don't reference entity fields in a way that needs this.
"""

from dataclasses import dataclass
from typing import Any

from app.models.metamodel import Entity

# Deliberately narrower than the frontend's own list (which also allows
# "formula"): a formula field's result type isn't declared anywhere on the
# field — it's just an AST — so the backend can't guarantee SUM/AVG/MIN/MAX
# over it actually produces a number. The frontend's looser check is a UX
# nicety; this is the real gate, so it only trusts types SQL can aggregate.
_NUMERIC_FIELD_TYPES = {"number", "decimal", "currency"}

_ALLOWED_AGGREGATIONS = {"count", "sum", "avg", "min", "max"}
_ALLOWED_FILTER_OPS = {"eq", "ne", "gt", "gte", "lt", "lte", "icontains"}


@dataclass
class BlockConfigError(Exception):
    """Raised with enough structure for the endpoint to return the exact
    {"message", "field", "reason"} shape the frontend can show inline."""

    field: str
    reason: str
    message: str = "Некорректная настройка отчёта"

    def __str__(self) -> str:
        return f"{self.field}: {self.reason}"


def validate_blocks(blocks: list[dict[str, Any]], entities_by_id: dict[str, Entity]) -> None:
    """Validate every block in a page's `blocks` list. Raises
    BlockConfigError on the first problem found."""
    for block in blocks:
        if block.get("type") == "pivot":
            _validate_pivot_config(block.get("config") or {}, entities_by_id)


def _validate_pivot_config(config: dict[str, Any], entities_by_id: dict[str, Entity]) -> None:
    entity_id = config.get("entity_id")
    if not entity_id:
        # No table picked yet — the frontend's own in-progress state while
        # the user is still filling out the block. Nothing to validate yet.
        return
    entity = entities_by_id.get(str(entity_id))
    if entity is None:
        raise BlockConfigError(
            field="entity_id",
            reason="Выбранная таблица не найдена в этом приложении",
        )
    fields_by_name = {f.name: f for f in entity.fields}

    for field_key in ("row_field", "col_field", "filter_field"):
        field_name = config.get(field_key)
        if field_name and field_name not in fields_by_name:
            raise BlockConfigError(
                field=field_key,
                reason=f"Поле «{field_name}» не найдено в выбранной таблице",
            )

    agg = config.get("agg") or "count"
    if agg not in _ALLOWED_AGGREGATIONS:
        raise BlockConfigError(
            field="agg",
            reason=f"Неизвестный способ расчёта: {agg!r}",
        )

    value_field_name = config.get("value_field")
    if value_field_name:
        value_field = fields_by_name.get(value_field_name)
        if value_field is None:
            raise BlockConfigError(
                field="value_field",
                reason=f"Поле «{value_field_name}» не найдено в выбранной таблице",
            )
        if agg != "count" and value_field.field_type not in _NUMERIC_FIELD_TYPES:
            raise BlockConfigError(
                field="value_field",
                reason=(
                    f"Для расчёта «{agg}» требуется числовое поле "
                    f"(число, десятичное или денежное), а не «{value_field.field_type}»"
                ),
            )
    elif agg != "count":
        raise BlockConfigError(
            field="value_field",
            reason=f"Для расчёта «{agg}» нужно выбрать показатель",
        )

    filter_op = config.get("filter_op")
    if filter_op and filter_op not in _ALLOWED_FILTER_OPS:
        raise BlockConfigError(
            field="filter_op",
            reason=f"Неизвестное условие фильтра: {filter_op!r}",
        )
    numeric_ops = {"gt", "gte", "lt", "lte"}
    filter_field_name = config.get("filter_field")
    if filter_op in numeric_ops and filter_field_name:
        filter_field = fields_by_name.get(filter_field_name)
        if filter_field is not None and filter_field.field_type not in _NUMERIC_FIELD_TYPES | {
            "date",
            "datetime",
        }:
            raise BlockConfigError(
                field="filter_op",
                reason=(
                    f"Условие «{filter_op}» применимо только к числовым или "
                    f"датовым полям, а не к «{filter_field.field_type}»"
                ),
            )
