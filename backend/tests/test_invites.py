"""Shareable app invite links: create, preview, sign up, accept, revoke, limits."""

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def owner(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="App Builder", is_system=True))
    user = User(
        email="owner@example.com", display_name="Owner", password_hash=hash_password("Owner1234!")
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="app_builder"))
    await db_session.flush()
    return user


@pytest.fixture()
async def outsider(db_session: AsyncSession) -> User:
    user = User(
        email="outsider@example.com",
        display_name="Outsider",
        password_hash=hash_password("Outsider1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _auth(client: AsyncClient, email: str, pwd: str) -> dict[str, str]:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _app(client: AsyncClient, h: dict[str, str]) -> str:
    r = await client.post("/api/v1/apps", json={"slug": "inv-app", "name": "Invite App"}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signup_via_link_grants_membership(client: AsyncClient, owner: User) -> None:
    h = await _auth(client, owner.email, "Owner1234!")
    app_id = await _app(client, h)

    r = await client.post(f"/api/v1/apps/{app_id}/invite-links", json={"role": "viewer"}, headers=h)
    assert r.status_code == 201, r.text
    token = r.json()["token"]

    r = await client.get(f"/api/v1/invites/{token}")
    assert r.status_code == 200
    assert r.json()["app_name"] == "Invite App"
    assert r.json()["role"] == "viewer"

    r = await client.post(
        f"/api/v1/invites/{token}/signup",
        json={"email": "newbie@example.com", "display_name": "Newbie", "password": "Newbie1234!"},
    )
    assert r.status_code == 201, r.text
    nh = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = await client.get(f"/api/v1/apps/{app_id}", headers=nh)
    assert r.status_code == 200

    members = (await client.get(f"/api/v1/apps/{app_id}/members", headers=h)).json()
    assert any(m["email"] == "newbie@example.com" and m["role"] == "viewer" for m in members)

    # Duplicate email → 409
    r = await client.post(
        f"/api/v1/invites/{token}/signup",
        json={"email": "newbie@example.com", "display_name": "Again", "password": "Newbie1234!"},
    )
    assert r.status_code == 409


@pytest.mark.integration
@pytest.mark.asyncio
async def test_accept_existing_user_and_max_uses(
    client: AsyncClient, owner: User, outsider: User
) -> None:
    h = await _auth(client, owner.email, "Owner1234!")
    app_id = await _app(client, h)
    token = (
        await client.post(
            f"/api/v1/apps/{app_id}/invite-links", json={"role": "editor", "max_uses": 1}, headers=h
        )
    ).json()["token"]

    oh = await _auth(client, outsider.email, "Outsider1234!")
    assert (await client.get(f"/api/v1/apps/{app_id}", headers=oh)).status_code == 404

    r = await client.post(f"/api/v1/invites/{token}/accept", headers=oh)
    assert r.status_code == 200, r.text
    assert r.json()["already_member"] is False
    assert (await client.get(f"/api/v1/apps/{app_id}", headers=oh)).status_code == 200

    # Single-use link is now exhausted
    assert (await client.get(f"/api/v1/invites/{token}")).status_code == 410


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_and_permissions(client: AsyncClient, owner: User, outsider: User) -> None:
    h = await _auth(client, owner.email, "Owner1234!")
    app_id = await _app(client, h)
    created = (await client.post(f"/api/v1/apps/{app_id}/invite-links", json={}, headers=h)).json()

    # Non-member cannot manage links
    oh = await _auth(client, outsider.email, "Outsider1234!")
    assert (
        await client.post(f"/api/v1/apps/{app_id}/invite-links", json={}, headers=oh)
    ).status_code == 403

    links = (await client.get(f"/api/v1/apps/{app_id}/invite-links", headers=h)).json()
    assert [link["id"] for link in links] == [created["id"]]
    assert "token" not in links[0]

    r = await client.delete(f"/api/v1/apps/{app_id}/invite-links/{created['id']}", headers=h)
    assert r.status_code == 204
    assert (await client.get(f"/api/v1/invites/{created['token']}")).status_code == 410
    assert (
        await client.post(f"/api/v1/invites/{created['token']}/accept", headers=oh)
    ).status_code == 410
    assert (await client.get("/api/v1/invites/garbage")).status_code == 410
