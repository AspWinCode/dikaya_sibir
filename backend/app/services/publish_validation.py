"""Pre-publish integrity check (ТЗ 3.11.1).

Checks four things across an app before it can be published:
  - blocks/pages without a data source (dangling entity_id)
  - rules with no actions (authored but never finished)
  - workflow transitions/initial states that reference a non-existent state
  - relations whose from_field_name/to_field_name no longer exists on the entity

Only "error"-severity issues block publication; "warning" is informational.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.logic import Rule
from app.models.metamodel import Entity, Field, Relation
from app.models.ui import Page
from app.models.workflow import StateDef, TransitionDef, WorkflowDef
from app.schemas.apps import PublishCheckResult, PublishIssue

# Block config keys that name an entity_id the block depends on for data.
_ENTITY_ID_BLOCK_TYPES = {
    "lookup",
    "responsible",
    "record_card",
    "pivot",
    "gantt",
    "tree",
    "import",
    "export",
    "filter_panel",
}
# view_type values whose page.layout.entity_id is the page's primary data source.
_DATA_VIEW_TYPES = {"table", "calendar", "deck", "gallery", "gantt", "map", "kanban"}


class PublishValidationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def check(self, app_id: uuid.UUID) -> PublishCheckResult:
        entities = (
            (await self._db.execute(select(Entity).where(Entity.app_id == app_id))).scalars().all()
        )
        entity_ids = {e.id for e in entities}

        issues: list[PublishIssue] = []
        issues += await self._check_pages(app_id, entity_ids)
        issues += await self._check_rules(app_id)
        issues += await self._check_workflows(app_id)
        issues += await self._check_relations(app_id)

        can_publish = not any(i.severity == "error" for i in issues)
        return PublishCheckResult(can_publish=can_publish, issues=issues)

    # ------------------------------------------------------------------
    # Blocks / pages without a data source
    # ------------------------------------------------------------------

    async def _check_pages(
        self,
        app_id: uuid.UUID,
        entity_ids: set[uuid.UUID],
    ) -> list[PublishIssue]:
        pages = (await self._db.execute(select(Page).where(Page.app_id == app_id))).scalars().all()

        issues: list[PublishIssue] = []
        for page in pages:
            layout = page.layout or {}
            if layout.get("view_type") in _DATA_VIEW_TYPES:
                issues.extend(
                    self._check_entity_ref(
                        layout.get("entity_id"),
                        entity_ids,
                        f"Страница «{page.title}» не привязана к источнику данных",
                        {"page_id": str(page.id)},
                    )
                )

            for block in page.blocks or []:
                block_type = block.get("type")
                config = block.get("config") or {}
                block_id = str(block.get("id") or "")

                if block_type in _ENTITY_ID_BLOCK_TYPES:
                    issues.extend(
                        self._check_entity_ref(
                            config.get("entity_id"),
                            entity_ids,
                            f"Блок «{block_type}» на странице «{page.title}» не привязан к таблице",
                            {"page_id": str(page.id), "block_id": block_id},
                        )
                    )
                elif block_type == "dropdown" and config.get("source") == "dynamic":
                    issues.extend(
                        self._check_entity_ref(
                            config.get("entity_id"),
                            entity_ids,
                            f"Список на странице «{page.title}» настроен на динамический "
                            "источник, но таблица не выбрана",
                            {"page_id": str(page.id), "block_id": block_id},
                        )
                    )
                elif block_type == "positions_picker":
                    for key, label in [
                        ("catalog_entity_id", "справочник товаров"),
                        ("positions_entity_id", "таблица позиций"),
                    ]:
                        issues.extend(
                            self._check_entity_ref(
                                config.get(key),
                                entity_ids,
                                f"Блок «Позиции заказа» на странице «{page.title}»: "
                                f"не выбран {label}",
                                {"page_id": str(page.id), "block_id": block_id},
                            )
                        )
        return issues

    @staticmethod
    def _check_entity_ref(
        raw_entity_id: Any,
        entity_ids: set[uuid.UUID],
        message: str,
        location: dict[str, str],
    ) -> list[PublishIssue]:
        if not raw_entity_id:
            return [
                PublishIssue(
                    severity="warning",
                    category="block_no_source",
                    message=message,
                    location=location,
                )
            ]
        try:
            valid = uuid.UUID(str(raw_entity_id)) in entity_ids
        except ValueError:
            valid = False
        if not valid:
            return [
                PublishIssue(
                    severity="error",
                    category="block_no_source",
                    message=f"{message} (ссылается на удалённую таблицу)",
                    location=location,
                )
            ]
        return []

    # ------------------------------------------------------------------
    # Rules with no actions
    # ------------------------------------------------------------------

    async def _check_rules(self, app_id: uuid.UUID) -> list[PublishIssue]:
        rules = (
            (
                await self._db.execute(
                    select(Rule).where(Rule.app_id == app_id, Rule.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )

        return [
            PublishIssue(
                severity="warning",
                category="rule_empty",
                message=f"Правило «{rule.name}» активно, но не содержит действий",
                location={"rule_id": str(rule.id)},
            )
            for rule in rules
            if not rule.actions
        ]

    # ------------------------------------------------------------------
    # Workflow transitions / states
    # ------------------------------------------------------------------

    async def _check_workflows(self, app_id: uuid.UUID) -> list[PublishIssue]:
        workflows = (
            (
                await self._db.execute(
                    select(WorkflowDef).where(
                        WorkflowDef.app_id == app_id, WorkflowDef.is_active.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )

        issues: list[PublishIssue] = []
        for wf in workflows:
            states = (
                (await self._db.execute(select(StateDef).where(StateDef.workflow_id == wf.id)))
                .scalars()
                .all()
            )
            state_names = {s.name for s in states}

            if wf.initial_state not in state_names:
                issues.append(
                    PublishIssue(
                        severity="error",
                        category="workflow_transition",
                        message=(
                            f"Процесс «{wf.name}»: начальный этап "
                            f"«{wf.initial_state}» не существует"
                        ),
                        location={"workflow_id": str(wf.id)},
                    )
                )

            transitions = (
                (
                    await self._db.execute(
                        select(TransitionDef).where(TransitionDef.workflow_id == wf.id)
                    )
                )
                .scalars()
                .all()
            )
            for tr in transitions:
                for state_name, side in [(tr.from_state, "из"), (tr.to_state, "в")]:
                    if state_name not in state_names:
                        issues.append(
                            PublishIssue(
                                severity="error",
                                category="workflow_transition",
                                message=(
                                    f"Процесс «{wf.name}»: переход «{tr.name}» ведёт {side} "
                                    f"несуществующий этап «{state_name}»"
                                ),
                                location={"workflow_id": str(wf.id), "transition_id": str(tr.id)},
                            )
                        )

            states_with_outgoing = {tr.from_state for tr in transitions}
            for state in states:
                if not state.is_terminal and state.name not in states_with_outgoing:
                    issues.append(
                        PublishIssue(
                            severity="warning",
                            category="workflow_transition",
                            message=(
                                f"Процесс «{wf.name}»: этап «{state.display_name}» "
                                "— тупик, нет переходов дальше"
                            ),
                            location={"workflow_id": str(wf.id), "state_id": str(state.id)},
                        )
                    )
        return issues

    # ------------------------------------------------------------------
    # Relations pointing at fields that no longer exist
    # ------------------------------------------------------------------

    async def _check_relations(self, app_id: uuid.UUID) -> list[PublishIssue]:
        relations = (
            (await self._db.execute(select(Relation).where(Relation.app_id == app_id)))
            .scalars()
            .all()
        )
        if not relations:
            return []

        entity_ids = {r.from_entity_id for r in relations} | {r.to_entity_id for r in relations}
        fields = (
            await self._db.execute(
                select(Field.entity_id, Field.name).where(Field.entity_id.in_(entity_ids))
            )
        ).all()
        field_names_by_entity: dict[uuid.UUID, set[str]] = {}
        for entity_id, name in fields:
            field_names_by_entity.setdefault(entity_id, set()).add(name)

        issues: list[PublishIssue] = []
        for rel in relations:
            if rel.from_field_name not in field_names_by_entity.get(rel.from_entity_id, set()):
                issues.append(
                    PublishIssue(
                        severity="error",
                        category="relation_invalid",
                        message=(
                            f"Связь «{rel.display_name or rel.from_field_name}»: поле "
                            f"«{rel.from_field_name}» больше не существует"
                        ),
                        location={"relation_id": str(rel.id)},
                    )
                )
            if rel.to_field_name and rel.to_field_name not in field_names_by_entity.get(
                rel.to_entity_id, set()
            ):
                issues.append(
                    PublishIssue(
                        severity="error",
                        category="relation_invalid",
                        message=(
                            f"Связь «{rel.display_name or rel.from_field_name}»: обратное поле "
                            f"«{rel.to_field_name}» больше не существует"
                        ),
                        location={"relation_id": str(rel.id)},
                    )
                )
        return issues
