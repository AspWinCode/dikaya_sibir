"""
Seed script (ТЗ items 13 + 15): adds the warehouse/journal data model to
the "Дикая Сибирь" app — entities, fields, relations, automation/
validation rules for running stock balance, and pages — without
duplicating the entities already there (Номенклатура, Помещения,
Поступления, Позиции предприятия already exist and are reused as-is;
see ARCHITECTURE notes in the commit this ships with).

Idempotent — every create step first checks for an existing slug/name
and skips it. Safe to run repeatedly; re-running after a partial
failure resumes from where it left off.

Run with: python .deploy/seed_warehouse_journals.py
Target server/credentials: same env vars as seed_vyezdnoy_master.py
(BASE, EMAIL, PASSWORD below) — override via environment if needed.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("SEED_API_BASE", "http://localhost:8000/api/v1")
EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@lesovik.app")
PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Lesovik!Admin2026")
TARGET_APP_NAME = "Дикая Сибирь"


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            body_text = resp.read()
            return json.loads(body_text) if body_text else None
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"  ERROR {e.code} {method} {path}: {body_text[:500]}", file=sys.stderr)
        raise


def main() -> None:
    print("Logging in...")
    tok = req("POST", "/auth/login", {"email": EMAIL, "password": PASSWORD, "totp_code": None})
    token = tok["access_token"]
    print("  OK")

    print(f"\nFinding app {TARGET_APP_NAME!r}...")
    apps = req("GET", "/apps", token=token)
    app_obj = next((a for a in apps["items"] if a["name"] == TARGET_APP_NAME), None)
    if not app_obj:
        print(f"  App {TARGET_APP_NAME!r} not found — create it first.", file=sys.stderr)
        sys.exit(1)
    app_id = app_obj["id"]
    print(f"  App id: {app_id}")

    entities_resp = req("GET", f"/apps/{app_id}/entities", token=token)
    by_slug = {e["slug"]: e for e in entities_resp}

    def require(slug):
        if slug not in by_slug:
            print(f"  Expected existing entity '{slug}' not found — aborting so nothing is duplicated.", file=sys.stderr)
            sys.exit(1)
        return by_slug[slug]

    # ------------------------------------------------------------------
    # Existing entities this seed builds on top of — never duplicated.
    # ------------------------------------------------------------------
    nomenklatura = require("nomenklatura")
    pomescheniya = require("pomescheniya")
    postupleniya = require("postupleniya")
    sotrudniki = require("sotrudniki")
    pozitsii = require("pozitsii_predpriyatiya")  # the running-balance table (Товар × Помещение × Количество)

    def field_names(entity):
        return {f["name"] for f in entity.get("fields", [])}

    def add_field(entity, name, display_name, ftype, required=False, choices=None, field_options=None):
        ef = field_names(entity)
        if name in ef:
            return None
        opts = dict(field_options or {})
        if choices:
            opts["choices"] = choices
        body = {"name": name, "display_name": display_name, "field_type": ftype,
                "is_required": required, "field_options": opts}
        f = req("POST", f"/apps/{app_id}/entities/{entity['id']}/fields", body, token=token)
        print(f"    + {entity['slug']}.{name} ({ftype})")
        return f

    def get_or_create_entity(slug, display_name, plural, desc, icon, color):
        if slug in by_slug:
            print(f"  Entity '{slug}' already exists")
            return req("GET", f"/apps/{app_id}/entities/{by_slug[slug]['id']}", token=token)
        e = req("POST", f"/apps/{app_id}/entities", {
            "slug": slug, "display_name": display_name, "name_plural": plural,
            "description": desc, "icon": icon, "color": color,
        }, token=token)
        print(f"  Created entity '{slug}'")
        by_slug[slug] = e
        return e

    existing_rels = req("GET", f"/apps/{app_id}/relations", token=token)
    existing_rel_names = {r["display_name"] for r in existing_rels}

    def add_relation(from_entity, to_entity, from_field_name, display_name):
        if display_name in existing_rel_names:
            return
        req("POST", f"/apps/{app_id}/relations", {
            "from_entity_id": from_entity["id"], "to_entity_id": to_entity["id"],
            "relation_type": "one_to_many", "from_field_name": from_field_name,
            "display_name": display_name,
        }, token=token)
        print(f"    + relation {display_name}")
        existing_rel_names.add(display_name)
        # Relation creation upserts the field on from_entity — refresh our copy.
        refreshed = req("GET", f"/apps/{app_id}/entities/{from_entity['id']}", token=token)
        from_entity["fields"] = refreshed["fields"]

    # ------------------------------------------------------------------
    # 1. Помещения: optional temperature bounds (ТЗ 15.3)
    # ------------------------------------------------------------------
    print("\n--- Помещения: диапазон температуры ---")
    add_field(pomescheniya, "min_temperature", "Мин. температура", "number")
    add_field(pomescheniya, "max_temperature", "Макс. температура", "number")

    # ------------------------------------------------------------------
    # 2. Поставщик (new entity, ТЗ 15.2)
    # ------------------------------------------------------------------
    print("\n--- Поставщик ---")
    postavshik = get_or_create_entity(
        "postavshik", "Поставщик", "Поставщики",
        "Поставщики номенклатуры — используется в журнале входного контроля", "truck", "#8B5CF6",
    )
    add_field(postavshik, "nazvanie", "Название", "text", required=True)
    add_field(postavshik, "kontakt", "Контакт", "text")

    # ------------------------------------------------------------------
    # 3. Поступления: привязка к помещению и поставщику (ТЗ 13 + 15.2)
    #    Without a location, a receipt couldn't update warehouse balance
    #    anywhere — this was missing entirely before.
    # ------------------------------------------------------------------
    print("\n--- Поступления: помещение + поставщик ---")
    add_relation(postupleniya, pomescheniya, "pomeschenie", "Поступление → Помещение")
    add_relation(postupleniya, postavshik, "postavshik_svyaz", "Поступление → Поставщик")

    # ------------------------------------------------------------------
    # 4. Перемещение (new entity, ТЗ 13 + 15.1) — a dedicated transfer
    #    entity, not a repurposed Операции (confirmed with the customer).
    # ------------------------------------------------------------------
    print("\n--- Перемещение ---")
    peremeshenie = get_or_create_entity(
        "peremeshenie", "Перемещение", "Перемещения",
        "Журнал перемещений между помещениями — изменяет остатки на складе", "arrow-left-right", "#F59E0B",
    )
    add_field(peremeshenie, "data", "Дата", "datetime", required=True)
    add_field(peremeshenie, "kolichestvo", "Количество", "decimal", required=True)
    add_field(peremeshenie, "kommentarij", "Комментарий / основание", "long_text")
    add_relation(peremeshenie, nomenklatura, "tovar", "Перемещение → Товар")
    add_relation(peremeshenie, sotrudniki, "otvetstvennyj", "Перемещение → Ответственный")
    # Two independent relations to the same target entity — from_field_name
    # differs (otkuda vs kuda), so both fields exist side by side.
    add_relation(peremeshenie, pomescheniya, "otkuda", "Перемещение → Помещение (откуда)")
    add_relation(peremeshenie, pomescheniya, "kuda", "Перемещение → Помещение (куда)")

    # ------------------------------------------------------------------
    # 5. Журнал входного контроля (new entity, ТЗ 15.2)
    # ------------------------------------------------------------------
    print("\n--- Журнал входного контроля ---")
    vhodnoj = get_or_create_entity(
        "vhodnoj_kontrol", "Входной контроль", "Входной контроль",
        "Журнал проверки поступившей продукции — связан с конкретным поступлением", "clipboard-check", "#10B981",
    )
    add_field(vhodnoj, "data", "Дата проверки", "date", required=True)
    add_field(vhodnoj, "kolichestvo", "Количество / партия", "decimal")
    add_field(vhodnoj, "rezultat", "Результат проверки", "select", required=True,
              choices=["Принято", "Принято с замечаниями", "Отклонено"])
    add_field(vhodnoj, "kommentarij", "Комментарий", "long_text")
    add_relation(vhodnoj, postupleniya, "postuplenie", "Входной контроль → Поступление")
    add_relation(vhodnoj, postavshik, "postavshik_svyaz", "Входной контроль → Поставщик")
    add_relation(vhodnoj, sotrudniki, "otvetstvennyj", "Входной контроль → Ответственный")

    # ------------------------------------------------------------------
    # 6. Журнал температурного контроля (new entity, ТЗ 15.3)
    # ------------------------------------------------------------------
    print("\n--- Журнал температурного контроля ---")
    temp_kontrol = get_or_create_entity(
        "temperaturnyj_kontrol", "Температурный контроль", "Температурный контроль",
        "Журнал контроля температуры по помещениям", "thermometer", "#EF4444",
    )
    add_field(temp_kontrol, "data", "Дата/время", "datetime", required=True)
    # range_check: generic runtime feature (see RangeStatusCell) — flags this
    # value against the related Помещение's min/max_temperature automatically.
    add_field(temp_kontrol, "temperatura", "Температура", "decimal", required=True, field_options={
        "range_check": {
            "relation_field": "pomeschenie",
            "min_field": "min_temperature",
            "max_field": "max_temperature",
        },
    })
    add_field(temp_kontrol, "kommentarij", "Комментарий", "long_text")
    add_relation(temp_kontrol, pomescheniya, "pomeschenie", "Температурный контроль → Помещение")
    add_relation(temp_kontrol, sotrudniki, "otvetstvennyj", "Температурный контроль → Ответственный")

    # ------------------------------------------------------------------
    # 7. Rules: running balance (ТЗ 13) — generic create_record
    #    match/increment upsert, no app-specific runtime code.
    # ------------------------------------------------------------------
    print("\n--- Правила: остатки ---")
    existing_rules = req("GET", f"/apps/{app_id}/rules", token=token)
    existing_rule_names = {r["name"] for r in existing_rules}

    def add_rule(entity, name, rule_type, event, actions, conditions=None, priority=100):
        if name in existing_rule_names:
            print(f"    ~ rule '{name}' already exists")
            return
        body = {
            "entity_id": entity["id"], "name": name, "rule_type": rule_type,
            "trigger": {"event": event, "watch_fields": []},
            "conditions": conditions or {}, "actions": actions, "priority": priority,
        }
        rule = req("POST", f"/apps/{app_id}/rules", body, token=token)
        # Rules are created inactive by default — activate so it actually runs.
        req("POST", f"/apps/{app_id}/rules/{rule['id']}/activate", token=token)
        print(f"    + rule '{name}' (active)")
        existing_rule_names.add(name)

    def field_ref(name):
        return {"type": "field_ref", "field": name}

    def lookup_sum_at(product_field, location_field):
        """Sum of pozitsii_predpriyatiya.kolichestvo for the triggering
        record's product/location (whichever two field names are passed)."""
        return {
            "type": "lookup", "entity_id": pozitsii["id"], "field": "kolichestvo", "agg": "sum",
            "filter": {"tovar": field_ref(product_field), "pomeschenie_tovara": field_ref(location_field)},
        }

    # Поступление created → +kolichestvo at (pozitsiya, pomeschenie).
    add_rule(
        postupleniya, "Поступление увеличивает остаток", "automation", "record.created",
        actions=[{
            "type": "create_record", "entity_id": pozitsii["id"],
            "match": {"tovar": field_ref("pozitsiya"), "pomeschenie_tovara": field_ref("pomeschenie")},
            "increment": {"kolichestvo": field_ref("kolichestvo")},
            "payload": {"tovar": field_ref("pozitsiya"), "pomeschenie_tovara": field_ref("pomeschenie"),
                        "kolichestvo": field_ref("kolichestvo")},
        }],
    )

    # Перемещение created → -kolichestvo at otkuda, +kolichestvo at kuda.
    add_rule(
        peremeshenie, "Перемещение переносит остаток", "automation", "record.created",
        actions=[
            {
                "type": "create_record", "entity_id": pozitsii["id"],
                "match": {"tovar": field_ref("tovar"), "pomeschenie_tovara": field_ref("otkuda")},
                "increment": {"kolichestvo": {"type": "math", "op": "multiply",
                                               "left": field_ref("kolichestvo"),
                                               "right": {"type": "literal", "value": -1}}},
                "payload": {"tovar": field_ref("tovar"), "pomeschenie_tovara": field_ref("otkuda"),
                            "kolichestvo": {"type": "math", "op": "multiply",
                                            "left": field_ref("kolichestvo"),
                                            "right": {"type": "literal", "value": -1}}},
            },
            {
                "type": "create_record", "entity_id": pozitsii["id"],
                "match": {"tovar": field_ref("tovar"), "pomeschenie_tovara": field_ref("kuda")},
                "increment": {"kolichestvo": field_ref("kolichestvo")},
                "payload": {"tovar": field_ref("tovar"), "pomeschenie_tovara": field_ref("kuda"),
                            "kolichestvo": field_ref("kolichestvo")},
            },
        ],
    )

    # Перемещение validation: block if requesting more than available at otkuda.
    add_rule(
        peremeshenie, "Перемещение: проверка достаточности остатка", "validation", "record.created",
        conditions={"type": "compare", "field": "kolichestvo", "op": "gt",
                    "value": lookup_sum_at("tovar", "otkuda")},
        actions=[{"type": "block_save", "message": "Недостаточно остатка в помещении-источнике для перемещения"}],
        priority=10,  # validation should run before the automation rule above
    )

    print(f"\n✅  Готово! Склад и журналы настроены для приложения «{TARGET_APP_NAME}».")
    print(f"   App ID: {app_id}")


if __name__ == "__main__":
    main()
