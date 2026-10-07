"""Tests for POST /workflow/{id}/instances/{id}/cancel."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def admin(db_session: AsyncSession) -> User:
    for role_id, display in [
        ("platform_admin", "Platform Admin"),
        ("app_builder", "Builder"),
    ]:
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name=display, is_system=True))
    user = User(
        email="cancel_admin@example.com",
        display_name="Cancel Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    for role_id in ("platform_admin", "app_builder"):
        db_session.add(UserRole(user_id=user.id, role_id=role_id))
    await db_session.flush()
    return user


@pytest.fixture()
async def regular_user(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="Builder", is_system=True))
    user = User(
        email="cancel_regular@example.com",
        display_name="Regular",
        password_hash=hash_password("User1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _create_app_and_workflow(
    client: AsyncClient, token: str, db_session: AsyncSession
) -> tuple[str, str, str]:
    """Return (app_id, workflow_id, instance_id)."""
    slug = f"wf-cancel-{uuid.uuid4().hex[:6]}"
    app_r = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Cancel Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app_r.status_code == 201, app_r.text
    app_id = app_r.json()["id"]

    entity_r = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "tickets", "display_name": "Tickets"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert entity_r.status_code == 201, entity_r.text
    entity_id = entity_r.json()["id"]

    field_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "title", "display_name": "Title", "field_type": "text"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert field_r.status_code == 201, field_r.text

    wf_r = await client.post(
        f"/api/v1/apps/{app_id}/workflows",
        json={"name": "Ticket Flow", "initial_state": "open", "entity_id": entity_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert wf_r.status_code == 201, wf_r.text
    workflow_id = wf_r.json()["id"]

    # Add states & transitions so the workflow is usable
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/states",
        json={"name": "open", "display_name": "Open", "is_terminal": False},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Activate it
    await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )

    record_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"title": "Test ticket"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert record_r.status_code == 201, record_r.text
    record_id = record_r.json()["id"]

    inst_r = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances",
        json={"record_id": record_id, "record_payload": {"title": "Test ticket"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert inst_r.status_code == 201, inst_r.text
    instance_id = inst_r.json()["id"]

    return app_id, workflow_id, instance_id


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_cancel_requires_auth(client: AsyncClient, admin: User) -> None:
    token = await _login(client, "cancel_admin@example.com", "Admin1234!")
    app_id, workflow_id, instance_id = await _create_app_and_workflow(client, token, None)
    r = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances/{instance_id}/cancel",
        json={"reason": "Test"},
    )
    assert r.status_code == 401


@pytest.mark.anyio
async def test_cancel_forbidden_for_regular_user(
    client: AsyncClient, admin: User, regular_user: User
) -> None:
    admin_token = await _login(client, "cancel_admin@example.com", "Admin1234!")
    app_id, workflow_id, instance_id = await _create_app_and_workflow(client, admin_token, None)

    # Membership (as a non-admin role) is required for the 403 role check to be
    # reached at all - without it, app visibility is checked first and a
    # non-member gets 404, not 403 (deliberate: don't leak app existence).
    member_r = await client.post(
        f"/api/v1/apps/{app_id}/members",
        json={"user_id": str(regular_user.id), "role": "editor"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert member_r.status_code == 204, member_r.text

    user_token = await _login(client, "cancel_regular@example.com", "User1234!")
    r = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances/{instance_id}/cancel",
        json={"reason": "Should not work"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_cancel_instance_success(client: AsyncClient, admin: User) -> None:
    token = await _login(client, "cancel_admin@example.com", "Admin1234!")
    app_id, workflow_id, instance_id = await _create_app_and_workflow(client, token, None)

    r = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances/{instance_id}/cancel",
        json={"reason": "Integration test cancel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["current_state"] == "__cancelled__"
    assert data["completed_at"] is not None


@pytest.mark.anyio
async def test_cancel_already_cancelled_returns_422(client: AsyncClient, admin: User) -> None:
    token = await _login(client, "cancel_admin@example.com", "Admin1234!")
    app_id, workflow_id, instance_id = await _create_app_and_workflow(client, token, None)

    # Cancel once
    r1 = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances/{instance_id}/cancel",
        json={"reason": "First cancel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200

    # Cancel again → 422
    r2 = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances/{instance_id}/cancel",
        json={"reason": "Second cancel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 422


@pytest.mark.anyio
async def test_cancel_nonexistent_instance_returns_404(client: AsyncClient, admin: User) -> None:
    token = await _login(client, "cancel_admin@example.com", "Admin1234!")
    app_id, workflow_id, _ = await _create_app_and_workflow(client, token, None)

    fake_id = str(uuid.uuid4())
    r = await client.post(
        f"/api/v1/apps/{app_id}/workflows/{workflow_id}/instances/{fake_id}/cancel",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
