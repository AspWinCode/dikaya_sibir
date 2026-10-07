import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.anyio


@pytest.fixture()
async def template_admin(db_session: AsyncSession) -> User:
    for role_id in ("app_builder", "platform_admin"):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name=role_id, is_system=True))
    user = User(
        email=f"template-admin-{uuid.uuid4().hex[:8]}@example.com",
        display_name="Template Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


async def _token(client, user: User) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Admin1234!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _app(client, token: str) -> str:
    r = await client.post(
        "/api/v1/apps",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": f"template-{uuid.uuid4().hex[:8]}", "name": "Template app"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_template_catalog_contains_required_templates(client, template_admin):
    token = await _token(client, template_admin)
    app_id = await _app(client, token)
    r = await client.get(
        f"/api/v1/apps/{app_id}/templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    ids = {t["id"] for t in r.json()}
    assert {
        "trading_company",
        "manufacturing_company",
        "service_company",
        "hr_department",
        "document_flow",
        "financial_accounting",
        "empty",
    } <= ids


async def test_template_install_installs_module_set(client, template_admin):
    token = await _token(client, template_admin)
    app_id = await _app(client, token)
    r = await client.post(
        f"/api/v1/apps/{app_id}/templates/manufacturing_company/install",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert {"enterprise", "warehouse", "production", "finance", "analytics"} <= set(
        body["modules_installed"]
    )
    assert body["entities_created"] >= 10
    assert body["fields_created"] >= 20

    modules = await client.get(
        "/api/v1/modules",
        params={"app_id": app_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert modules.status_code == 200, modules.text
    installed = {m["code"] for m in modules.json() if m["installed"]}
    assert {"enterprise", "warehouse", "production", "finance", "analytics"} <= installed
