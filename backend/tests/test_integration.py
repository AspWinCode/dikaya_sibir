"""
Integration layer tests.

Unit:  HMAC signing, event pattern matching, secret generation.
Integration: webhook subscription CRUD, rotate_secret, delivery history,
             OutboxWriter.
"""

import hashlib
import hmac
import uuid

import pytest
from app.core.http_client import (
    compute_signature,
    generate_secret,
    matches_event,
    subscription_matches,
)
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.integration import OutboxWriter
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ==================================================================
# Unit: HMAC + event matching
# ==================================================================


class TestComputeSignature:
    def test_format(self) -> None:
        sig = compute_signature("mysecret", b"hello")
        assert sig.startswith("sha256=")
        assert len(sig) == len("sha256=") + 64  # 32 bytes hex = 64 chars

    def test_deterministic(self) -> None:
        body = b'{"event": "test"}'
        s1 = compute_signature("secret", body)
        s2 = compute_signature("secret", body)
        assert s1 == s2

    def test_different_secrets_differ(self) -> None:
        body = b"payload"
        assert compute_signature("secret1", body) != compute_signature("secret2", body)

    def test_different_bodies_differ(self) -> None:
        s = "secret"
        assert compute_signature(s, b"body1") != compute_signature(s, b"body2")

    def test_verifiable_with_stdlib(self) -> None:
        secret = "verifytest"
        body = b'{"foo": "bar"}'
        sig = compute_signature(secret, body)
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert sig == expected


class TestGenerateSecret:
    def test_length(self) -> None:
        s = generate_secret()
        assert len(s) == 64  # 32 bytes → 64 hex chars

    def test_uniqueness(self) -> None:
        secrets = {generate_secret() for _ in range(100)}
        assert len(secrets) == 100

    def test_hex_chars_only(self) -> None:
        s = generate_secret()
        assert all(c in "0123456789abcdef" for c in s)


class TestMatchesEvent:
    def test_wildcard_matches_all(self) -> None:
        assert matches_event("*", "record.created")
        assert matches_event("*", "workflow.transitioned")
        assert matches_event("*", "anything.at.all")

    def test_prefix_wildcard(self) -> None:
        assert matches_event("record.*", "record.created")
        assert matches_event("record.*", "record.updated")
        assert matches_event("record.*", "record.deleted")
        assert not matches_event("record.*", "workflow.transitioned")
        assert not matches_event("record.*", "records.created")  # prefix must match exactly

    def test_exact_match(self) -> None:
        assert matches_event("record.created", "record.created")
        assert not matches_event("record.created", "record.updated")

    def test_prefix_wildcard_exact_prefix(self) -> None:
        # "record.*" should also match "record" itself
        assert matches_event("record.*", "record")

    def test_empty_pattern_no_match(self) -> None:
        assert not matches_event("", "record.created")


class TestSubscriptionMatches:
    def test_any_pattern_matches(self) -> None:
        assert subscription_matches(["record.created", "workflow.*"], "workflow.transitioned")

    def test_no_pattern_matches(self) -> None:
        assert not subscription_matches(["record.created"], "workflow.transitioned")

    def test_wildcard_in_list(self) -> None:
        assert subscription_matches(["*"], "anything")

    def test_empty_list_no_match(self) -> None:
        assert not subscription_matches([], "record.created")


# ==================================================================
# Fixtures
# ==================================================================


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email=f"int_builder_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Int Builder",
        password_hash=hash_password("Build1234!"),
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


async def _setup_app(client: AsyncClient, token: str) -> str:
    slug = f"int-app-{uuid.uuid4().hex[:6]}"
    r = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Integration Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ==================================================================
# Integration: subscription CRUD
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_webhook(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/webhooks",
        json={
            "name": "My Webhook",
            "target_url": "https://example.com/hook",
            "events": ["record.*", "workflow.transitioned"],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Webhook"
    assert data["is_active"] is True
    assert "secret" in data  # shown only on creation
    assert len(data["secret"]) == 64  # 32 bytes hex
    assert data["events"] == ["record.*", "workflow.transitioned"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_secret_not_in_get_response(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/webhooks",
        json={"name": "W", "target_url": "https://example.com/h"},
        headers=headers,
    )
    sub_id = create.json()["id"]

    get_resp = await client.get(f"/api/v1/apps/{app_id}/webhooks/{sub_id}", headers=headers)
    assert get_resp.status_code == 200
    assert "secret" not in get_resp.json()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_webhooks(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/webhooks"

    await client.post(base, json={"name": "W1", "target_url": "https://a.com/1"}, headers=headers)
    await client.post(base, json={"name": "W2", "target_url": "https://a.com/2"}, headers=headers)

    resp = await client.get(base, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_webhook(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/webhooks"

    sub = (
        await client.post(
            base,
            json={"name": "Old", "target_url": "https://a.com/h"},
            headers=headers,
        )
    ).json()

    resp = await client.patch(
        f"{base}/{sub['id']}",
        json={"name": "New Name", "is_active": False, "events": ["*"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["is_active"] is False
    assert resp.json()["events"] == ["*"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_webhook(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/webhooks"

    sub = (
        await client.post(
            base, json={"name": "Del", "target_url": "https://a.com/h"}, headers=headers
        )
    ).json()

    assert (await client.delete(f"{base}/{sub['id']}", headers=headers)).status_code == 204
    assert (await client.get(f"{base}/{sub['id']}", headers=headers)).status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_not_found(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(f"/api/v1/apps/{app_id}/webhooks/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_active_only_filter(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/webhooks"

    active = (
        await client.post(
            base, json={"name": "Active", "target_url": "https://a.com/1"}, headers=headers
        )
    ).json()
    inactive = (
        await client.post(
            base, json={"name": "Inactive", "target_url": "https://a.com/2"}, headers=headers
        )
    ).json()

    await client.patch(f"{base}/{inactive['id']}", json={"is_active": False}, headers=headers)

    resp = await client.get(f"{base}?active_only=true", headers=headers)
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()]
    assert active["id"] in ids
    assert inactive["id"] not in ids


# ==================================================================
# Integration: rotate_secret
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rotate_secret(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/webhooks"

    create_resp = await client.post(
        base, json={"name": "R", "target_url": "https://a.com/h"}, headers=headers
    )
    sub_id = create_resp.json()["id"]
    original_secret = create_resp.json()["secret"]

    rotate_resp = await client.post(f"{base}/{sub_id}/rotate_secret", headers=headers)
    assert rotate_resp.status_code == 200
    new_secret = rotate_resp.json()["secret"]

    assert new_secret != original_secret
    assert len(new_secret) == 64


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delivery_history_empty(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/apps/{app_id}/webhooks"

    sub = (
        await client.post(
            base, json={"name": "D", "target_url": "https://a.com/h"}, headers=headers
        )
    ).json()

    resp = await client.get(f"{base}/{sub['id']}/deliveries", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ==================================================================
# Integration: schema validation
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_target_url(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/webhooks",
        json={"name": "Bad URL", "target_url": "ftp://example.com/hook"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_empty_events_list_rejected(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _setup_app(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/webhooks",
        json={"name": "W", "target_url": "https://a.com/h", "events": []},
        headers=headers,
    )
    assert resp.status_code == 422


# ==================================================================
# Unit: OutboxWriter (DB)
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_outbox_writer_publishes(db_session: AsyncSession) -> None:
    from app.models.integration import Outbox
    from sqlalchemy import select

    app_id = uuid.uuid4()
    entry = await OutboxWriter.publish(
        db_session,
        app_id=app_id,
        event_type="record.created",
        payload={"record_id": str(uuid.uuid4())},
        dedup_key="test-dedup-1",
    )
    await db_session.flush()

    result = await db_session.execute(select(Outbox).where(Outbox.id == entry.id))
    row = result.scalar_one()
    assert row.event_type == "record.created"
    assert row.status == "pending"
    assert row.dedup_key == "test-dedup-1"
    assert row.app_id == app_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_outbox_writer_auto_dedup_key(db_session: AsyncSession) -> None:
    """No dedup_key → auto-generated, unique per call."""
    app_id = uuid.uuid4()
    e1 = await OutboxWriter.publish(db_session, app_id, "test.event", {})
    e2 = await OutboxWriter.publish(db_session, app_id, "test.event", {})
    await db_session.flush()

    assert e1.dedup_key != e2.dedup_key
