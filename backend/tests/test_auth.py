"""Auth endpoint tests.

These are integration tests — they require a running PostgreSQL (see conftest.py).
Mark: pytest -m integration
"""

import pytest
from app.core.security import hash_password
from app.models.identity import User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def active_user(db_session: AsyncSession) -> User:
    user = User(
        email="auth_test@example.com",
        display_name="Auth Tester",
        password_hash=hash_password("StrongPass1!"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, active_user: User) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": active_user.email, "password": "StrongPass1!"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, active_user: User) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": active_user.email, "password": "WrongPassword1!"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Whatever1!"},
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_token_rotation(client: AsyncClient, active_user: User) -> None:
    # Login
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": active_user.email, "password": "StrongPass1!"},
    )
    tokens = login.json()

    # Refresh
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_refresh_token_reuse_rejected(client: AsyncClient, active_user: User) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": active_user.email, "password": "StrongPass1!"},
    )
    old_refresh = login.json()["refresh_token"]

    # First use — should succeed and rotate
    await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})

    # Second use of the same token — must be rejected
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_current_user(client: AsyncClient, active_user: User) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": active_user.email, "password": "StrongPass1!"},
    )
    token = login.json()["access_token"]

    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == active_user.email


@pytest.mark.integration
@pytest.mark.asyncio
async def test_logout_revokes_token(client: AsyncClient, active_user: User) -> None:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": active_user.email, "password": "StrongPass1!"},
    )
    tokens = login.json()

    # Logout
    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp.status_code == 204

    # Refreshing revoked token must fail
    resp2 = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert resp2.status_code == 401
