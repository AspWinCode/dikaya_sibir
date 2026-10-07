"""
Sprint 9 — Production Readiness tests.

Unit:
  - FieldRestrictions.filter_payload / check_write
  - Rate limit key extraction
  - Metrics registry (counters exist and are incrementable)

Integration:
  - Field permission CRUD (list, bulk-upsert, delete)
  - ABAC enforcement: denied fields stripped from record reads
  - /health/ready endpoint
  - /health/live endpoint
"""

import uuid
from typing import ClassVar

import pytest
from app.core.rate_limit import _extract_user_key
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.security import ABACService, FieldRestrictions
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ==================================================================
# Unit: FieldRestrictions
# ==================================================================


class TestFieldRestrictions:
    def test_filter_payload_no_restrictions(self) -> None:
        r = FieldRestrictions(entity_id=uuid.uuid4())
        payload = {"name": "Alice", "salary": 100000, "email": "a@b.com"}
        assert r.filter_payload(payload) == payload

    def test_filter_payload_strips_denied(self) -> None:
        r = FieldRestrictions(entity_id=uuid.uuid4(), denied_read={"salary", "ssn"})
        payload = {"name": "Alice", "salary": 100000, "ssn": "123-45", "email": "a@b.com"}
        result = r.filter_payload(payload)
        assert "salary" not in result
        assert "ssn" not in result
        assert result["name"] == "Alice"
        assert result["email"] == "a@b.com"

    def test_filter_payload_unknown_denied_field(self) -> None:
        """Denied field not present in payload → no error."""
        r = FieldRestrictions(entity_id=uuid.uuid4(), denied_read={"nonexistent"})
        payload = {"name": "Alice"}
        assert r.filter_payload(payload) == {"name": "Alice"}

    def test_check_write_no_restrictions(self) -> None:
        r = FieldRestrictions(entity_id=uuid.uuid4())
        assert r.check_write(["name", "salary"]) == []

    def test_check_write_returns_denied(self) -> None:
        r = FieldRestrictions(entity_id=uuid.uuid4(), denied_write={"salary"})
        denied = r.check_write(["name", "salary", "email"])
        assert denied == ["salary"]

    def test_check_write_multiple_denied(self) -> None:
        r = FieldRestrictions(entity_id=uuid.uuid4(), denied_write={"salary", "ssn"})
        denied = set(r.check_write(["name", "salary", "ssn", "email"]))
        assert denied == {"salary", "ssn"}

    def test_to_response(self) -> None:
        r = FieldRestrictions(
            entity_id=uuid.uuid4(),
            denied_read={"salary"},
            denied_write={"salary", "ssn"},
        )
        resp = r.to_response()
        assert resp.denied_read == ["salary"]
        assert set(resp.denied_write) == {"salary", "ssn"}


# ==================================================================
# Unit: rate limit key extraction
# ==================================================================


class TestRateLimitKey:
    def _make_request(self, auth_header: str | None = None) -> object:
        """Build a minimal Request-like mock."""

        class FakeClient:
            host = "1.2.3.4"

        class FakeRequest:
            client = FakeClient()
            headers: ClassVar[dict] = {}

        req = FakeRequest()
        if auth_header:
            req.headers = {"Authorization": auth_header}
        return req  # type: ignore[return-value]

    def test_no_auth_uses_ip(self) -> None:
        req = self._make_request()
        key = _extract_user_key(req)  # type: ignore[arg-type]
        assert key == "ip:1.2.3.4"

    def test_invalid_bearer_falls_back_to_ip(self) -> None:
        req = self._make_request("Bearer not.a.jwt")
        key = _extract_user_key(req)  # type: ignore[arg-type]
        assert key.startswith("ip:")

    def test_valid_jwt_payload_uses_sub(self) -> None:
        import base64
        import json

        # Craft a minimal JWT with sub claim (no real signature needed for this unit test)
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
        payload = (
            base64.urlsafe_b64encode(json.dumps({"sub": "user-123"}).encode()).rstrip(b"=").decode()
        )
        token = f"{header}.{payload}.fakesig"

        req = self._make_request(f"Bearer {token}")
        key = _extract_user_key(req)  # type: ignore[arg-type]
        assert key == "user:user-123"


# ==================================================================
# Unit: metrics registry
# ==================================================================


class TestMetricsRegistry:
    def test_counters_importable(self) -> None:
        from app.core.metrics import (
            auth_attempts,
            file_uploads,
            record_operations,
            rule_executions,
            webhook_deliveries,
            workflow_transitions,
        )

        # All are prometheus Counter objects — should be incrementable
        rule_executions.labels(status="success").inc(0)
        workflow_transitions.labels(workflow_id="wf1", from_state="a", to_state="b").inc(0)
        record_operations.labels(operation="read").inc(0)
        webhook_deliveries.labels(status="delivered").inc(0)
        auth_attempts.labels(result="success").inc(0)
        file_uploads.labels(status="success").inc(0)

    def test_gauge_importable(self) -> None:
        from app.core.metrics import workflow_instances_active

        workflow_instances_active.set(0)  # should not raise


# ==================================================================
# Fixtures
# ==================================================================


@pytest.fixture()
async def admin_user(db_session: AsyncSession) -> User:
    for role_id in ("platform_admin", "app_builder"):
        if not await db_session.get(Role, role_id):
            db_session.add(
                Role(id=role_id, display_name=role_id.replace("_", " ").title(), is_system=True)
            )
    user = User(
        email=f"sec_admin_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Sec Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    for role_id in ("platform_admin", "app_builder"):
        db_session.add(UserRole(user_id=user.id, role_id=role_id))
    await db_session.flush()
    return user


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _setup_app_entity(client: AsyncClient, token: str) -> tuple[str, str]:
    slug = f"sec-app-{uuid.uuid4().hex[:6]}"
    app_r = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Sec App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app_r.status_code == 201
    app_id = app_r.json()["id"]

    ent_r = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "employee", "display_name": "Employee"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ent_r.status_code == 201
    return app_id, ent_r.json()["id"]


# ==================================================================
# Integration: health endpoints
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_live(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_ready(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert "ready" in data
    assert "database" in data
    assert "redis" in data


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_full(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "version" in data
    assert "checks" in data
    assert "database" in data["checks"]


# ==================================================================
# Integration: field permission CRUD
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_permissions_empty(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id = await _setup_app_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/permissions",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bulk_upsert_permissions(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id = await _setup_app_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/apps/{app_id}/entities/{entity_id}/permissions"

    body = {
        "permissions": [
            {
                "field_name": "salary",
                "role_id": "data_viewer",
                "can_read": False,
                "can_write": False,
            },
            {"field_name": "salary", "role_id": "data_editor", "can_read": True, "can_write": True},
            {
                "field_name": "password",
                "role_id": "data_viewer",
                "can_read": False,
                "can_write": False,
            },
        ]
    }
    resp = await client.put(url, json=body, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    # Verify persisted
    list_resp = await client.get(url, headers=headers)
    assert len(list_resp.json()) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bulk_upsert_replaces_all(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id = await _setup_app_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/apps/{app_id}/entities/{entity_id}/permissions"

    await client.put(
        url,
        json={
            "permissions": [
                {
                    "field_name": "salary",
                    "role_id": "data_viewer",
                    "can_read": False,
                    "can_write": False,
                },
                {
                    "field_name": "ssn",
                    "role_id": "data_viewer",
                    "can_read": False,
                    "can_write": False,
                },
            ]
        },
        headers=headers,
    )

    # Replace with only one row
    r2 = await client.put(
        url,
        json={
            "permissions": [
                {
                    "field_name": "salary",
                    "role_id": "data_viewer",
                    "can_read": False,
                    "can_write": False,
                },
            ]
        },
        headers=headers,
    )
    assert len(r2.json()) == 1

    list_r = await client.get(url, headers=headers)
    assert len(list_r.json()) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_permission(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id = await _setup_app_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/apps/{app_id}/entities/{entity_id}/permissions"

    upsert = await client.put(
        url,
        json={
            "permissions": [
                {
                    "field_name": "salary",
                    "role_id": "data_viewer",
                    "can_read": False,
                    "can_write": False,
                },
            ]
        },
        headers=headers,
    )
    perm_id = upsert.json()[0]["id"]

    del_resp = await client.delete(f"{url}/{perm_id}", headers=headers)
    assert del_resp.status_code == 204

    list_resp = await client.get(url, headers=headers)
    assert list_resp.json() == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_check_my_permissions(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id = await _setup_app_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/apps/{app_id}/entities/{entity_id}/permissions"

    await client.put(
        url,
        json={
            "permissions": [
                {
                    "field_name": "salary",
                    "role_id": "data_viewer",
                    "can_read": False,
                    "can_write": False,
                },
            ]
        },
        headers=headers,
    )

    check = await client.get(f"{url}/check", headers=headers)
    assert check.status_code == 200
    # admin_user has platform_admin + app_builder, not data_viewer → no restrictions
    data = check.json()
    assert data["denied_read"] == []
    assert data["denied_write"] == []


# ==================================================================
# Integration: ABAC enforcement in ABACService (unit-level DB test)
# ==================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_restrictions_deny_wins(db_session: AsyncSession) -> None:
    """If any role denies a field, the field is denied regardless of other roles."""
    from app.schemas.security import FieldPermissionBulkUpsert, FieldPermissionUpsert

    entity_id = uuid.uuid4()
    app_id = uuid.uuid4()

    # role_a allows salary, role_b denies salary
    svc = ABACService(db_session)
    await svc.bulk_upsert(
        app_id,
        entity_id,
        FieldPermissionBulkUpsert(
            permissions=[
                FieldPermissionUpsert(
                    field_name="salary", role_id="role_a", can_read=True, can_write=True
                ),
                FieldPermissionUpsert(
                    field_name="salary", role_id="role_b", can_read=False, can_write=False
                ),
            ]
        ),
    )

    # user has both roles → deny wins
    restrictions = await svc.get_restrictions(entity_id, ["role_a", "role_b"])
    assert "salary" in restrictions.denied_read
    assert "salary" in restrictions.denied_write


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_restrictions_no_rows_allows_all(db_session: AsyncSession) -> None:
    entity_id = uuid.uuid4()
    svc = ABACService(db_session)
    restrictions = await svc.get_restrictions(entity_id, ["data_viewer", "data_editor"])
    assert restrictions.denied_read == set()
    assert restrictions.denied_write == set()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_filter_payload_abac(db_session: AsyncSession) -> None:
    from app.schemas.security import FieldPermissionBulkUpsert, FieldPermissionUpsert

    entity_id = uuid.uuid4()
    app_id = uuid.uuid4()
    svc = ABACService(db_session)

    await svc.bulk_upsert(
        app_id,
        entity_id,
        FieldPermissionBulkUpsert(
            permissions=[
                FieldPermissionUpsert(
                    field_name="ssn", role_id="data_viewer", can_read=False, can_write=False
                ),
            ]
        ),
    )

    restrictions = await svc.get_restrictions(entity_id, ["data_viewer"])
    payload = {"name": "Alice", "ssn": "123-45-6789", "email": "a@b.com"}
    filtered = restrictions.filter_payload(payload)

    assert "ssn" not in filtered
    assert filtered["name"] == "Alice"
    assert filtered["email"] == "a@b.com"
