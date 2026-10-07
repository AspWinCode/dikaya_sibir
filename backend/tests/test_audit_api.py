"""Tests for GET /audit — requires platform_admin."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.audit import AuditService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def admin(db_session: AsyncSession) -> User:
    for role_id, display in [("platform_admin", "Platform Admin")]:
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name=display, is_system=True))
    user = User(
        email="audit_admin@example.com",
        display_name="Audit Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    await db_session.flush()
    return user


@pytest.fixture()
async def regular_user(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="Builder", is_system=True))
    user = User(
        email="audit_user@example.com",
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


async def _seed_log(db_session: AsyncSession, user_id: uuid.UUID, action: str, **kwargs) -> None:
    await AuditService(db_session).log(action, user_id=user_id, **kwargs)
    await db_session.flush()


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_audit_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/audit")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_audit_forbidden_for_regular_user(client: AsyncClient, regular_user: User) -> None:
    token = await _login(client, "audit_user@example.com", "User1234!")
    r = await client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


@pytest.mark.anyio
async def test_audit_returns_list_for_admin(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    await _seed_log(
        db_session, admin.id, "test.action", resource_type="record", resource_id=str(uuid.uuid4())
    )
    token = await _login(client, "audit_admin@example.com", "Admin1234!")
    r = await client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_audit_filter_by_action(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    unique_action = f"unique.action.{uuid.uuid4().hex[:6]}"
    await _seed_log(db_session, admin.id, unique_action)
    await _seed_log(db_session, admin.id, "other.action")
    token = await _login(client, "audit_admin@example.com", "Admin1234!")
    r = await client.get(
        f"/api/v1/audit?action={unique_action}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert all(e["action"] == unique_action for e in data)


@pytest.mark.anyio
async def test_audit_filter_by_user_id(
    client: AsyncClient, admin: User, regular_user: User, db_session: AsyncSession
) -> None:
    unique_action = f"user_action.{uuid.uuid4().hex[:6]}"
    await _seed_log(db_session, regular_user.id, unique_action)
    token = await _login(client, "audit_admin@example.com", "Admin1234!")
    r = await client.get(
        f"/api/v1/audit?action={unique_action}&user_id={regular_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert all(e["user_id"] == str(regular_user.id) for e in data)


@pytest.mark.anyio
async def test_audit_limit_respected(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    unique_action = f"bulk.{uuid.uuid4().hex[:6]}"
    for _ in range(5):
        await _seed_log(db_session, admin.id, unique_action)
    token = await _login(client, "audit_admin@example.com", "Admin1234!")
    r = await client.get(
        f"/api/v1/audit?action={unique_action}&limit=3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert len(r.json()) <= 3


@pytest.mark.anyio
async def test_audit_entry_schema(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    resource_id = str(uuid.uuid4())
    unique_action = f"schema.check.{uuid.uuid4().hex[:6]}"
    await _seed_log(
        db_session,
        admin.id,
        unique_action,
        resource_type="record",
        resource_id=resource_id,
        level="info",
    )
    token = await _login(client, "audit_admin@example.com", "Admin1234!")
    r = await client.get(
        f"/api/v1/audit?action={unique_action}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    entry = r.json()[0]
    assert "id" in entry
    assert "action" in entry
    assert "created_at" in entry
    assert entry["resource_type"] == "record"
    assert entry["resource_id"] == resource_id
