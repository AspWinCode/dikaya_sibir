import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.anyio


@pytest.fixture()
async def module_admin(db_session: AsyncSession) -> User:
    for role_id in ("app_builder", "platform_admin"):
        existing = await db_session.get(Role, role_id)
        if not existing:
            db_session.add(
                Role(id=role_id, display_name=role_id.replace("_", " ").title(), is_system=True)
            )
    user = User(
        email=f"module-admin-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Module Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


async def _login_admin(client, user: User):
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Admin1234!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _create_app(client, token: str) -> str:
    r = await client.post(
        "/api/v1/apps",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "slug": f"modules-{uuid.uuid4().hex[:8]}",
            "name": "Module test app",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_list_module_catalog(client, module_admin):
    token = await _login_admin(client, module_admin)
    r = await client.get("/api/v1/modules", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    codes = {m["code"] for m in r.json()}
    assert {"enterprise", "warehouse", "finance", "documents", "it_support"} <= codes


async def test_install_module_installs_dependencies_and_manifest(client, module_admin):
    token = await _login_admin(client, module_admin)
    app_id = await _create_app(client, token)

    r = await client.post(
        f"/api/v1/apps/{app_id}/modules/warehouse/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["module"]["code"] == "warehouse"
    assert "enterprise" in body["installed_dependencies"]
    assert body["entities_created"] >= 4
    assert body["fields_created"] >= 8

    installed = await client.get(
        f"/api/v1/apps/{app_id}/modules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert installed.status_code == 200, installed.text
    assert {"enterprise", "warehouse"} <= {m["module_code"] for m in installed.json()}

    entities = await client.get(
        f"/api/v1/apps/{app_id}/entities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert entities.status_code == 200, entities.text
    assert {"departments", "products", "stock_balances"} <= {e["slug"] for e in entities.json()}


async def test_install_module_is_idempotent(client, module_admin):
    token = await _login_admin(client, module_admin)
    app_id = await _create_app(client, token)

    first = await client.post(
        f"/api/v1/apps/{app_id}/modules/analytics/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await client.post(
        f"/api/v1/apps/{app_id}/modules/analytics/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["entities_created"] == 0
    assert second.json()["fields_created"] == 0
    assert second.json()["pages_created"] == 0


async def test_documents_module_creates_registry_fields_and_sequence(client, module_admin):
    token = await _login_admin(client, module_admin)
    app_id = await _create_app(client, token)

    install = await client.post(
        f"/api/v1/apps/{app_id}/modules/documents/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert install.status_code == 200, install.text

    entities = await client.get(
        f"/api/v1/apps/{app_id}/entities",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert entities.status_code == 200, entities.text
    by_slug = {entity["slug"]: entity for entity in entities.json()}
    assert {"documents", "filing_cases"} <= set(by_slug)

    document_fields = {field["name"]: field for field in by_slug["documents"]["fields"]}
    assert document_fields["number"]["field_type"] == "autonumber"
    assert {"title", "case_code", "registered_at", "retention_until"} <= set(document_fields)

    case_fields = {field["name"] for field in by_slug["filing_cases"]["fields"]}
    assert {"code", "index", "retention_years", "export_ready"} <= case_fields

    sequences = await client.get(
        f"/api/v1/apps/{app_id}/entities/{by_slug['documents']['id']}/sequences",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sequences.status_code == 200, sequences.text
    sequence = next(item for item in sequences.json() if item["field_name"] == "number")
    assert sequence["prefix"] == "DOC-"
    assert sequence["padding"] == 6

    preview = await client.post(
        f"/api/v1/apps/{app_id}/entities/{by_slug['documents']['id']}/sequences/{sequence['id']}/next",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["value"] == "DOC-000001"


async def test_uninstall_module_marks_removed(client, module_admin):
    token = await _login_admin(client, module_admin)
    app_id = await _create_app(client, token)
    install = await client.post(
        f"/api/v1/apps/{app_id}/modules/documents/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert install.status_code == 200, install.text

    delete = await client.delete(
        f"/api/v1/apps/{app_id}/modules/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete.status_code == 204, delete.text

    catalog = await client.get(
        "/api/v1/modules",
        params={"app_id": app_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert catalog.status_code == 200, catalog.text
    documents = next(m for m in catalog.json() if m["code"] == "documents")
    assert documents["installed"] is False
