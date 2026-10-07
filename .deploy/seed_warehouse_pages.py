"""
Seed script (ТЗ items 13 + 15, navigation part): gives the entities added
by seed_warehouse_journals.py (Помещения — already existed but had no page
at all; Поставщик; Перемещение; Входной контроль; Температурный контроль)
real top-level pages, so a user sees a "Склад" / "Журнал" section in the
app's own navigation instead of having to find these tables in a technical
schema list. Also relabels the two existing pages that already cover part
of the warehouse flow (Позиции предприятия → остатки; Поступления) with a
"Склад:" prefix so they read as one coherent section — the platform has no
separate nav-group concept, so a shared title prefix plus contiguous
nav_order is the simplest way to group them without a new generic feature.

Idempotent — every page is looked up by slug first; a page already created
by a prior run is left alone (only re-labeled pages are re-checked by title
so a manual rename afterwards sticks).

Run with: python .deploy/seed_warehouse_pages.py
Must run AFTER seed_warehouse_journals.py (needs the entities it creates).
"""
import json
import os
import sys
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
        print(f"  App {TARGET_APP_NAME!r} not found.", file=sys.stderr)
        sys.exit(1)
    app_id = app_obj["id"]
    print(f"  App id: {app_id}")

    entities = req("GET", f"/apps/{app_id}/entities", token=token)
    by_slug = {e["slug"]: e for e in entities}

    def require(slug):
        if slug not in by_slug:
            print(f"  Expected entity '{slug}' not found — run seed_warehouse_journals.py first.", file=sys.stderr)
            sys.exit(1)
        return by_slug[slug]

    pomescheniya = require("pomescheniya")
    postavshik = require("postavshik")
    peremeshenie = require("peremeshenie")
    vhodnoj = require("vhodnoj_kontrol")
    temp_kontrol = require("temperaturnyj_kontrol")

    pages = req("GET", f"/apps/{app_id}/pages", token=token)
    by_page_slug = {p["slug"]: p for p in pages}
    by_page_title = {p["title"]: p for p in pages}

    # ------------------------------------------------------------------
    # Relabel the two existing pages so the "Склад" section reads as one
    # group. Only the title changes — slug/layout/blocks untouched.
    # ------------------------------------------------------------------
    def relabel(old_title, new_title, nav_order):
        p = by_page_title.get(old_title) or by_page_title.get(new_title)
        if not p:
            print(f"  ! page '{old_title}' not found, skipping relabel")
            return
        if p["title"] == new_title and p["nav_order"] == nav_order:
            print(f"  ~ '{new_title}' already labeled")
            return
        req("PATCH", f"/apps/{app_id}/pages/{p['id']}", {"title": new_title, "nav_order": nav_order}, token=token)
        print(f"  renamed '{old_title}' -> '{new_title}' (nav_order={nav_order})")

    print("\n--- Relabeling existing Склад pages ---")
    relabel("Позиции предприятия", "Склад: Остатки", 10)
    relabel("Поступления", "Склад: Поступления", 12)

    # ------------------------------------------------------------------
    # New pages: one list page (+ one system form page bound to the same
    # entity) per entity that doesn't have a top-level page yet, mirroring
    # the exact minimal shape the editor itself generates (confirmed
    # against an existing page+form pair in prod): list page has
    # layout.view_type + entity_id and a single "Новая запись" button
    # block pointing at the form page's id; form page has view_type="form"
    # and a single empty "form" block (the form block auto-renders every
    # field from layout.entity_id — no per-field config needed).
    # ------------------------------------------------------------------
    def page_slug(entity):
        return entity["slug"].replace("_", "-")

    def ensure_form_page(entity, title):
        slug = f"entity-form-seed-{page_slug(entity)}"
        if slug in by_page_slug:
            return by_page_slug[slug]["id"]
        p = req("POST", f"/apps/{app_id}/pages", {
            "slug": slug,
            "title": title,
            "layout": {"entity_id": entity["id"], "is_system": True, "view_type": "form", "system_type": "form"},
            "blocks": [{"id": f"id-{slug}-form", "type": "form", "title": "Форма ввода", "config": {}}],
        }, token=token)
        req("POST", f"/apps/{app_id}/pages/{p['id']}/publish", token=token)
        by_page_slug[slug] = p
        print(f"  + form page '{title}'")
        return p["id"]

    def ensure_list_page(entity, title, nav_order, button_label, view_type="table"):
        slug = f"{page_slug(entity)}-seed"
        if slug in by_page_slug:
            print(f"  ~ list page '{title}' already exists")
            return
        form_page_id = ensure_form_page(entity, button_label)
        p = req("POST", f"/apps/{app_id}/pages", {
            "slug": slug,
            "title": title,
            "nav_order": nav_order,
            "layout": {"entity_id": entity["id"], "view_type": view_type, "sort": [], "group_by": [], "hidden_columns": []},
            "blocks": [{
                "id": f"id-{slug}-btn", "type": "button", "title": button_label,
                "config": {"label": button_label, "actionType": "page", "targetPageId": form_page_id, "width": "half"},
            }],
        }, token=token)
        req("POST", f"/apps/{app_id}/pages/{p['id']}/publish", token=token)
        by_page_slug[slug] = p
        print(f"  + list page '{title}' (nav_order={nav_order})")

    print("\n--- Новые страницы: Склад ---")
    ensure_list_page(pomescheniya, "Склад: Помещения", 11, "Новое помещение")
    ensure_list_page(postavshik, "Склад: Поставщики", 13, "Новый поставщик")

    print("\n--- Новые страницы: Журналы ---")
    ensure_list_page(peremeshenie, "Журнал: Перемещения", 14, "Новое перемещение")
    ensure_list_page(vhodnoj, "Журнал: Входной контроль", 15, "Новая запись контроля")
    ensure_list_page(temp_kontrol, "Журнал: Температурный контроль", 16, "Новое измерение")

    print(f"\n✅  Готово! Навигация «Склад» / «Журналы» настроена для «{TARGET_APP_NAME}».")


if __name__ == "__main__":
    main()
