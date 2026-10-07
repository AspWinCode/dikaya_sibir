"""Seed: create "Учёт номенклатуры" demo app.

Run once on the server:
    docker exec lesovik-backend python -m app.seeds.nomenclature_app

Idempotent — skips creation if the app slug already exists.
"""

import asyncio
import uuid

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.models.catalog import App
from app.models.identity import User
from app.models.metamodel import Entity, Field, FieldType, Relation, RelationType
from app.models.ui import Page

configure_logging()
log = structlog.get_logger(__name__)

APP_SLUG = "uchet-nomenklatury"


# ── helpers ────────────────────────────────────────────────────────────────


def _field(
    entity_id: uuid.UUID,
    app_id: uuid.UUID,
    name: str,
    display_name: str,
    field_type: str,
    order: int,
    options: dict | None = None,
    required: bool = False,
) -> Field:
    return Field(
        entity_id=entity_id,
        app_id=app_id,
        name=name,
        display_name=display_name,
        field_type=field_type,
        is_required=required,
        display_order=order,
        field_options=options or {},
    )


# ── main ───────────────────────────────────────────────────────────────────


async def run() -> None:
    async with AsyncSessionLocal() as db:
        # 0. Guard — skip if already seeded
        existing = (await db.execute(select(App).where(App.slug == APP_SLUG))).scalar_one_or_none()
        if existing:
            log.info("nomenclature_app_exists", app_id=str(existing.id))
            return

        # 1. Find platform admin to use as owner
        owner = (
            (await db.execute(select(User).where(User.is_superuser.is_(True)))).scalars().first()
        )
        if not owner:
            log.error("no_superuser_found")
            return

        # 2. Create app
        app = App(
            slug=APP_SLUG,
            name="Учёт номенклатуры",
            description="Ввод номенклатуры и просмотр отчётов",
            owner_id=owner.id,
        )
        db.add(app)
        await db.flush()
        log.info("app_created", slug=APP_SLUG, app_id=str(app.id))

        # 3. Entity: Категория
        cat = Entity(
            app_id=app.id,
            slug="kategoriya",
            display_name="Категория",
            icon="🗂️",
            color="#35A7FF",
            field_order=[],
        )
        db.add(cat)
        await db.flush()

        cat_fields = [
            _field(cat.id, app.id, "name", "Название", FieldType.TEXT, 0, required=True),
        ]
        for f in cat_fields:
            db.add(f)
        await db.flush()
        cat.field_order = [str(f.id) for f in cat_fields]

        log.info("entity_created", slug="kategoriya")

        # 4. Entity: Номенклатура
        nom = Entity(
            app_id=app.id,
            slug="nomenklatura",
            display_name="Номенклатура",
            icon="📦",
            color="#20BE4F",
            field_order=[],
        )
        db.add(nom)
        await db.flush()

        nom_fields = [
            _field(
                nom.id, app.id, "naimenovanie", "Наименование", FieldType.TEXT, 0, required=True
            ),
            _field(nom.id, app.id, "artikul", "Артикул", FieldType.TEXT, 1),
            _field(
                nom.id,
                app.id,
                "edinitsa",
                "Единица измерения",
                FieldType.SELECT,
                2,
                options={"choices": ["шт", "кг", "л", "м", "уп"]},
            ),
            _field(nom.id, app.id, "tsena", "Цена", FieldType.CURRENCY, 3),
            _field(nom.id, app.id, "ostatok", "Остаток", FieldType.NUMBER, 4),
            _field(nom.id, app.id, "opisanie", "Описание", FieldType.LONG_TEXT, 5),
        ]
        for f in nom_fields:
            db.add(f)
        await db.flush()
        nom.field_order = [str(f.id) for f in nom_fields]

        log.info("entity_created", slug="nomenklatura")

        # 5. Relation: Номенклатура N:1 Категория
        relation = Relation(
            app_id=app.id,
            from_entity_id=nom.id,
            to_entity_id=cat.id,
            relation_type=RelationType.ONE_TO_MANY,
            from_field_name="kategoriya_id",
            display_name="Категория",
        )
        db.add(relation)

        # Also add FK field to Номенклатура so it's visible
        fk_field = _field(
            nom.id,
            app.id,
            "kategoriya_id",
            "Категория",
            FieldType.RELATION,
            6,
            options={"target_entity_slug": "kategoriya"},
        )
        db.add(fk_field)
        await db.flush()
        nom.field_order = [*nom.field_order, str(fk_field.id)]

        log.info("relation_created", from_entity="nomenklatura", to_entity="kategoriya")

        # 6. Pages
        pages = [
            Page(
                app_id=app.id,
                slug="nomenklatura",
                title="Номенклатура",
                icon="📦",
                nav_order=0,
                is_published=True,
                blocks=[
                    {
                        "id": str(uuid.uuid4()),
                        "type": "table",
                        "config": {
                            "entity_slug": "nomenklatura",
                            "fields": [
                                "naimenovanie",
                                "artikul",
                                "edinitsa",
                                "tsena",
                                "ostatok",
                                "kategoriya_id",
                            ],
                        },
                    }
                ],
            ),
            Page(
                app_id=app.id,
                slug="dobavit-tovar",
                title="Добавить товар",
                icon="➕",
                nav_order=1,
                is_published=True,
                blocks=[
                    {
                        "id": str(uuid.uuid4()),
                        "type": "form",
                        "config": {
                            "entity_slug": "nomenklatura",
                            "fields": [
                                "naimenovanie",
                                "artikul",
                                "edinitsa",
                                "tsena",
                                "ostatok",
                                "kategoriya_id",
                                "opisanie",
                            ],
                            "submit_label": "Сохранить",
                        },
                    }
                ],
            ),
            Page(
                app_id=app.id,
                slug="otchyoty",
                title="Отчёты",
                icon="📊",
                nav_order=2,
                is_published=True,
                blocks=[
                    {
                        "id": str(uuid.uuid4()),
                        "type": "metric",
                        "config": {
                            "entity_slug": "nomenklatura",
                            "field": "ostatok",
                            "aggregation": "sum",
                            "label": "Общий остаток",
                        },
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "type": "metric",
                        "config": {
                            "entity_slug": "nomenklatura",
                            "field": "id",
                            "aggregation": "count",
                            "label": "Позиций в каталоге",
                        },
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "type": "chart",
                        "config": {
                            "entity_slug": "nomenklatura",
                            "chart_type": "bar",
                            "group_by": "kategoriya_id",
                            "value_field": "ostatok",
                            "label": "Остатки по категориям",
                        },
                    },
                    {
                        "id": str(uuid.uuid4()),
                        "type": "table",
                        "config": {
                            "entity_slug": "nomenklatura",
                            "fields": [
                                "naimenovanie",
                                "artikul",
                                "tsena",
                                "ostatok",
                                "kategoriya_id",
                            ],
                            "label": "Полный список",
                        },
                    },
                ],
            ),
        ]
        for page in pages:
            db.add(page)

        await db.commit()
        log.info("nomenclature_app_seeded", app_id=str(app.id), pages=len(pages))
        print(f"\n✅ Приложение создано! ID: {app.id}")
        print("   Откройте: http://155.212.164.251:8090/editor\n")


if __name__ == "__main__":
    asyncio.run(run())
