"""User CRUD endpoint tests."""

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def admin_user(db_session: AsyncSession) -> User:
    # platform_admin role is seeded by the init migration; only add if missing
    existing_role = await db_session.get(Role, "platform_admin")
    if not existing_role:
        db_session.add(Role(id="platform_admin", display_name="Platform Admin", is_system=True))
        await db_session.flush()
    user = User(
        email="admin@example.com",
        display_name="Admin",
        password_hash=hash_password("AdminPass1!"),
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    await db_session.flush()
    return user


async def _login(client: AsyncClient, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_user_as_admin(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "AdminPass1!")
    resp = await client.post(
        "/api/v1/users",
        json={
            "email": "newuser@example.com",
            "display_name": "New User",
            "password": "NewPass12345!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "AdminPass1!")
    payload = {"email": "dup@example.com", "display_name": "Dup", "password": "DupPass12345!"}

    await client.post("/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"})
    resp = await client.post(
        "/api/v1/users", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_user_forbidden_for_non_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    regular = User(
        email="regular@example.com",
        display_name="Regular",
        password_hash=hash_password("Regular12!"),
    )
    db_session.add(regular)
    await db_session.flush()

    token = await _login(client, "regular@example.com", "Regular12!")
    resp = await client.post(
        "/api/v1/users",
        json={"email": "x@example.com", "display_name": "Xx User", "password": "Xxxx12345!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_users_requires_admin_or_auditor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = User(
        email="viewer@example.com",
        display_name="Viewer",
        password_hash=hash_password("Viewer123!"),
    )
    db_session.add(user)
    await db_session.flush()

    token = await _login(client, "viewer@example.com", "Viewer123!")
    resp = await client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invite_forces_password_change(
    client: AsyncClient, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail_send(*_a: object, **_kw: object) -> bool:
        return False

    monkeypatch.setattr("app.services.email.send_email", _fail_send)
    token = await _login(client, admin_user.email, "AdminPass1!")
    resp = await client.post(
        "/api/v1/users/invite",
        json={"email": "invited@example.com", "display_name": "Invited"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # Delivery failed → admin gets the temp password back
    assert data["email_sent"] is False
    temp = data["temp_password"]
    assert temp and data["must_change_password"] is True

    h = {"Authorization": f"Bearer {await _login(client, 'invited@example.com', temp)}"}
    assert (await client.get("/api/v1/users/me", headers=h)).status_code == 200
    blocked = await client.get("/api/v1/apps", headers=h)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Password change required"

    r = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": temp, "new_password": "BrandNewPass123!"},
        headers=h,
    )
    assert r.status_code == 204, r.text

    h2 = {
        "Authorization": f"Bearer {await _login(client, 'invited@example.com', 'BrandNewPass123!')}"
    }
    assert (await client.get("/api/v1/apps", headers=h2)).status_code == 200
    me = (await client.get("/api/v1/users/me", headers=h2)).json()
    assert me["must_change_password"] is False
