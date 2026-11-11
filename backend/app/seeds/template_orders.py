"""Seed: template project "Шаблон: Учёт заказов" (a ready-made demo app).

A small shop: Клиенты, Товары, Заказы — tables with relations, forms and
sample data, plus automation (sum calculation, validation).  Built through the
same service layer the UI/API uses, so everything it creates opens and edits
like a hand-made project.

Run on the server:
    docker exec lesovik-backend python -m app.seeds.template_orders --dry-run
    docker exec lesovik-backend python -m app.seeds.template_orders \
        --members roma_99_99@mail.ru:admin other@example.com:editor

  --dry-run   build everything, print the summary, then ROLL BACK (nothing saved)
  --owner     owner e-mail (default: the first superuser)
  --members   e-mail[:role] pairs to add as app members (role: admin|editor|viewer,
              default admin). Members are NOT added unless you pass them.

Idempotent: if the app slug already exists nothing is created.
Atomic: one transaction — any failure leaves the database untouched.
"""

import argparse
import asyncio
import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.models.catalog import App
from app.models.identity import User
from app.models.metamodel import FieldType, RelationType
from app.schemas.apps import AppCreate, AppMemberAdd
from app.schemas.entities import EntityCreate, FieldCreate, RelationCreate
from app.schemas.records import RecordCreate
from app.schemas.rules import RuleCreate, RuleTrigger, RuleType, TriggerEvent
from app.schemas.ui import PageCreate
from app.services.apps import AppService
from app.services.entities import EntityService
from app.services.records import RecordService
from app.services.rules import RuleService
from app.services.ui import UIService

configure_logging()
log = structlog.get_logger(__name__)

APP_SLUG = "template-orders"
APP_NAME = "Шаблон: Учёт заказов"

CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Томск", "Другой"]
CATEGORIES = ["Мёд", "Чай и травы", "Орехи", "Ягоды", "Подарочные наборы"]
STATUSES = ["Новый", "В работе", "Выполнен", "Отменён"]


def _f(name: str, title: str, ftype: FieldType, **kw: Any) -> FieldCreate:
    return FieldCreate(name=name, display_name=title, field_type=ftype, **kw)


async def _make_entity(
    es: EntityService,
    ui: UIService,
    app_id: uuid.UUID,
    slug: str,
    title: str,
    plural: str,
    icon: str,
    color: str,
    fields: list[FieldCreate],
    nav_order: int,
) -> uuid.UUID:
    """Entity + its fields + the standard pages the editor normally makes
    (published table view and the detail/form/inline system pages)."""
    ent = await es.create_entity(
        app_id,
        EntityCreate(slug=slug, display_name=title, name_plural=plural, icon=icon, color=color),
    )
    for fc in fields:
        await es.create_field(app_id, ent.id, fc)

    eid = str(ent.id)
    page = await ui.create_page(
        app_id,
        PageCreate(
            slug=f"{slug}-table",
            title=title,
            icon=icon,
            nav_order=nav_order,
            layout={
                "entity_id": eid,
                "view_type": "table",
                "group_by": [],
                "hidden_columns": [],
                "sort": [],
            },
        ),
    )
    await ui.publish_page(app_id, page.id)
    for system_type, view_type in (("detail", "detail"), ("form", "form"), ("inline", "table")):
        await ui.create_page(
            app_id,
            PageCreate(
                slug=f"{slug}-{system_type}-sys",
                title=f"{title}_{system_type.capitalize()}",
                layout={
                    "is_system": True,
                    "system_type": system_type,
                    "entity_id": eid,
                    "view_type": view_type,
                },
            ),
        )
    return ent.id


async def build(db, owner: User, members: list[tuple[str, str]]) -> dict[str, Any]:
    apps, es, ui = AppService(db), EntityService(db), UIService(db)
    rules = RuleService(db)
    records = RecordService(db)

    app = await apps.create_app(
        AppCreate(
            slug=APP_SLUG,
            name=APP_NAME,
            description="Готовый демо-проект: клиенты, товары и заказы с автоматизацией",
            icon="🛒",
            color="#35A7FF",
            category="template",
        ),
        owner_id=owner.id,
    )
    aid = app.id

    # ── Tables ────────────────────────────────────────────────────────────
    klienty = await _make_entity(
        es, ui, aid, "klienty", "Клиенты", "Клиенты", "👤", "#35A7FF",
        [
            _f("fio", "ФИО", FieldType.TEXT, is_required=True),
            _f("telefon", "Телефон", FieldType.PHONE),
            _f("pochta", "Почта", FieldType.EMAIL),
            _f("gorod", "Город", FieldType.SELECT, field_options={"choices": CITIES}),
        ],
        nav_order=0,
    )
    tovary = await _make_entity(
        es, ui, aid, "tovary", "Товары", "Товары", "📦", "#20BE4F",
        [
            _f("nazvanie", "Название", FieldType.TEXT, is_required=True),
            _f("artikul", "Артикул", FieldType.TEXT),
            _f("kategoriya", "Категория", FieldType.SELECT, field_options={"choices": CATEGORIES}),
            _f("tsena", "Цена", FieldType.CURRENCY, is_required=True),
            _f("ostatok", "Остаток", FieldType.NUMBER),
        ],
        nav_order=1,
    )
    zakazy = await _make_entity(
        es, ui, aid, "zakazy", "Заказы", "Заказы", "🧾", "#F5A623",
        [
            _f("data", "Дата", FieldType.DATE),
            _f("status", "Статус", FieldType.SELECT, field_options={"choices": STATUSES}, default_value="Новый"),
            _f("kolichestvo", "Количество", FieldType.NUMBER, is_required=True),
            _f("tsena", "Цена за единицу", FieldType.CURRENCY, is_required=True),
            _f("summa", "Сумма", FieldType.CURRENCY),
            _f("kommentariy", "Комментарий", FieldType.LONG_TEXT),
        ],
        nav_order=2,
    )

    # ── Relations (Заказ → Клиент, Заказ → Товар); the service also adds the
    #    visible relation field on Заказы ─────────────────────────────────
    await es.create_relation(
        aid,
        RelationCreate(
            from_entity_id=zakazy, to_entity_id=klienty,
            relation_type=RelationType.ONE_TO_MANY, from_field_name="klient", display_name="Клиент",
        ),
    )
    await es.create_relation(
        aid,
        RelationCreate(
            from_entity_id=zakazy, to_entity_id=tovary,
            relation_type=RelationType.ONE_TO_MANY, from_field_name="tovar", display_name="Товар",
        ),
    )

    # ── Sample data (created BEFORE the rules so they don't interfere; the
    #    calculated fields are filled by hand here) ────────────────────────
    async def add(entity_id: uuid.UUID, payload: dict[str, Any]) -> str:
        rec = await records.create_record(entity_id, RecordCreate(payload=payload), aid, owner.id)
        return str(rec.id)

    clients = [
        await add(klienty, {"fio": "Иванов Сергей", "telefon": "+7 913 000-11-22", "pochta": "ivanov@example.com", "gorod": "Новосибирск"}),
        await add(klienty, {"fio": "Петрова Мария", "telefon": "+7 905 111-22-33", "pochta": "petrova@example.com", "gorod": "Томск"}),
        await add(klienty, {"fio": "Смирнов Алексей", "telefon": "+7 999 222-33-44", "pochta": "smirnov@example.com", "gorod": "Москва"}),
    ]
    goods_spec = [
        ("Мёд липовый 500 г", "MED-500", "Мёд", 650, 40),
        ("Кедровый орех очищенный 200 г", "ORH-200", "Орехи", 890, 25),
        ("Иван-чай ферментированный 100 г", "CHAY-100", "Чай и травы", 320, 60),
        ("Брусника сушёная 150 г", "YAG-150", "Ягоды", 410, 30),
        ("Набор «Сибирский завтрак»", "SET-001", "Подарочные наборы", 1890, 12),
    ]
    goods = [
        (await add(tovary, {"nazvanie": n, "artikul": a, "kategoriya": c, "tsena": p, "ostatok": q}), p)
        for n, a, c, p, q in goods_spec
    ]
    today = date.today()
    orders_spec = [
        (0, 0, 2, "Выполнен", 6), (1, 1, 1, "Выполнен", 5), (2, 2, 3, "В работе", 3),
        (0, 4, 1, "Новый", 2), (1, 3, 4, "Новый", 1), (2, 0, 5, "Отменён", 0),
    ]
    for ci, gi, qty, status, days_ago in orders_spec:
        gid, price = goods[gi]
        await add(zakazy, {
            "data": (today - timedelta(days=days_ago)).isoformat(),
            "status": status, "kolichestvo": qty, "tsena": price, "summa": qty * price,
            "klient": clients[ci], "tovar": gid,
        })

    # ── Automation / validation on Заказы ───────────────────────────────
    sum_expr = {
        "type": "math", "op": "multiply",
        "left": {"type": "field_ref", "field": "kolichestvo"},
        "right": {"type": "field_ref", "field": "tsena"},
    }
    created: list[Any] = []
    created.append(await rules.create_rule(aid, RuleCreate(
        entity_id=zakazy, name="Заказ: расчёт суммы при создании",
        description="Сумма = количество × цена за единицу",
        rule_type=RuleType.AUTOMATION, trigger=RuleTrigger(event=TriggerEvent.RECORD_CREATED),
        actions=[{"type": "set_field", "field": "summa", "value": sum_expr}], priority=100,
    ), owner.id))
    created.append(await rules.create_rule(aid, RuleCreate(
        entity_id=zakazy, name="Заказ: пересчёт суммы при изменении",
        description="Пересчитывает сумму, если изменили количество или цену",
        rule_type=RuleType.AUTOMATION,
        trigger=RuleTrigger(event=TriggerEvent.FIELD_CHANGED, watch_fields=["kolichestvo", "tsena"]),
        actions=[{"type": "set_field", "field": "summa", "value": sum_expr}], priority=100,
    ), owner.id))
    created.append(await rules.create_rule(aid, RuleCreate(
        entity_id=zakazy, name="Заказ: количество должно быть больше нуля",
        description="Не даёт сохранить заказ с нулевым или отрицательным количеством",
        rule_type=RuleType.VALIDATION, trigger=RuleTrigger(event=TriggerEvent.RECORD_CREATED),
        conditions={"type": "compare", "field": "kolichestvo", "op": "lte", "value": 0},
        actions=[{"type": "block_save", "message": "Количество должно быть больше нуля"}], priority=50,
    ), owner.id))
    for r in created:
        await rules.activate_rule(aid, r.id)

    # ── Members (only when asked for) ───────────────────────────────────
    added: list[str] = []
    for email, role in members:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            log.warning("member_not_found", email=email)
            continue
        if user.id == owner.id:
            continue
        await apps.add_member(aid, AppMemberAdd(user_id=user.id, role=role), owner.id)
        added.append(f"{email}:{role}")

    return {
        "app_id": str(aid),
        "tables": 3,
        "sample_records": len(clients) + len(goods) + len(orders_spec),
        "rules": len(created),
        "members_added": added,
    }


async def run(dry_run: bool, owner_email: str | None, members: list[tuple[str, str]]) -> None:
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(App).where(App.slug == APP_SLUG))).scalar_one_or_none():
            print(f"Приложение «{APP_NAME}» уже существует — ничего не создано.")
            return

        q = select(User).where(User.email == owner_email) if owner_email else select(User).where(User.is_superuser.is_(True))
        owner = (await db.execute(q)).scalars().first()
        if owner is None:
            print("Владелец не найден (нет суперпользователя / неверный --owner).")
            return

        try:
            summary = await build(db, owner, members)
        except Exception:
            await db.rollback()
            log.exception("template_orders_failed")
            raise

        if dry_run:
            await db.rollback()
            print(f"DRY-RUN OK (откат, ничего не сохранено): {summary}")
        else:
            await db.commit()
            print(f"✅ Шаблон создан: {summary}")


def _parse_members(items: list[str]) -> list[tuple[str, str]]:
    out = []
    for item in items:
        email, _, role = item.partition(":")
        out.append((email.strip(), (role or "admin").strip()))
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--owner")
    p.add_argument("--members", nargs="*", default=[])
    a = p.parse_args()
    asyncio.run(run(a.dry_run, a.owner, _parse_members(a.members)))
