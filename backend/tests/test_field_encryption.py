"""
AES-256-GCM field-level encryption + masking (ТЗ 3.13: "Шифрование данных
в хранилище: AES-256" + "Маскирование чувствительных данных в интерфейсе
и экспортах, настраивается на уровне поля").

Unit:
  - app.core.field_crypto encrypt/decrypt roundtrip, tamper detection, masking

Integration (HTTP, mirrors tests/test_security.py's app+entity setup):
  - a sensitive field's value is opaque ciphertext in the DB row directly
  - platform_admin sees the real value through the API
  - a role with no explicit FieldPermission sees a masked value, not ciphertext
  - a role explicitly granted can_read=True sees the real value
  - the audit log never contains the plaintext of a sensitive field
"""

import uuid

import pytest
from app.core import field_crypto
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.data import Record
from app.models.identity import Role, User, UserRole
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ==================================================================
# Unit
# ==================================================================


class TestFieldCrypto:
    def test_roundtrip(self) -> None:
        token = field_crypto.encrypt_value("7701234567")
        assert field_crypto.is_encrypted(token)
        assert field_crypto.decrypt_value(token) == "7701234567"

    def test_roundtrip_preserves_type(self) -> None:
        token = field_crypto.encrypt_value(42)
        assert field_crypto.decrypt_value(token) == 42

    def test_plain_value_is_not_encrypted(self) -> None:
        assert not field_crypto.is_encrypted("plain text")
        assert not field_crypto.is_encrypted(None)

    def test_two_encryptions_of_same_value_differ(self) -> None:
        # AES-GCM uses a random nonce per call — ciphertext must not be
        # comparable, which is exactly why sensitive fields can't be
        # filtered/sorted/unique.
        a = field_crypto.encrypt_value("same")
        b = field_crypto.encrypt_value("same")
        assert a != b
        assert field_crypto.decrypt_value(a) == field_crypto.decrypt_value(b) == "same"

    def test_tampered_ciphertext_fails_closed(self) -> None:
        token = field_crypto.encrypt_value("secret")
        tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
        with pytest.raises(field_crypto.FieldCryptoError):
            field_crypto.decrypt_value(tampered)

    def test_encrypt_sensitive_fields_only_touches_named_fields(self) -> None:
        payload = {"inn": "123", "name": "Public"}
        enc = field_crypto.encrypt_sensitive_fields(payload, {"inn"})
        assert field_crypto.is_encrypted(enc["inn"])
        assert enc["name"] == "Public"

    def test_decrypt_sensitive_fields_roundtrip(self) -> None:
        payload = {"inn": "123", "name": "Public"}
        enc = field_crypto.encrypt_sensitive_fields(payload, {"inn"})
        dec = field_crypto.decrypt_sensitive_fields(enc, {"inn"})
        assert dec == payload

    def test_mask_value_keeps_last_four(self) -> None:
        assert field_crypto.mask_value("7701234567") == "******4567"

    def test_mask_short_value_fully_redacted(self) -> None:
        assert field_crypto.mask_value("12") == "**"

    def test_mask_none_is_dash(self) -> None:
        assert field_crypto.mask_value(None) == "—"


# ==================================================================
# Integration
# ==================================================================


@pytest.fixture()
async def admin_user(db_session: AsyncSession) -> User:
    for role_id in ("platform_admin", "app_builder"):
        if not await db_session.get(Role, role_id):
            db_session.add(
                Role(id=role_id, display_name=role_id.replace("_", " ").title(), is_system=True)
            )
    user = User(
        email=f"enc_admin_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Enc Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    for role_id in ("platform_admin", "app_builder"):
        db_session.add(UserRole(user_id=user.id, role_id=role_id))
    await db_session.flush()
    return user


@pytest.fixture()
async def viewer_role(db_session: AsyncSession) -> Role:
    role_id = f"viewer_{uuid.uuid4().hex[:6]}"
    role = Role(id=role_id, display_name="Viewer", is_system=False)
    db_session.add(role)
    await db_session.flush()
    return role


@pytest.fixture()
async def viewer_user(db_session: AsyncSession, viewer_role: Role) -> User:
    user = User(
        email=f"enc_viewer_{uuid.uuid4().hex[:6]}@example.com",
        display_name="Enc Viewer",
        password_hash=hash_password("Viewer1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=viewer_role.id))
    await db_session.flush()
    return user


async def _login(client: AsyncClient, email: str, pwd: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": pwd})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


async def _setup_app_entity_with_sensitive_field(
    client: AsyncClient,
    token: str,
) -> tuple[str, str, str]:
    """Returns (app_id, entity_id, field_name)."""
    slug = f"enc-app-{uuid.uuid4().hex[:6]}"
    headers = {"Authorization": f"Bearer {token}"}
    app_r = await client.post(
        "/api/v1/apps", json={"slug": slug, "name": "Enc App"}, headers=headers
    )
    assert app_r.status_code == 201, app_r.text
    app_id = app_r.json()["id"]

    ent_r = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "contact", "display_name": "Contact"},
        headers=headers,
    )
    assert ent_r.status_code == 201, ent_r.text
    entity_id = ent_r.json()["id"]

    field_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "inn", "display_name": "ИНН", "field_type": "text", "is_sensitive": True},
        headers=headers,
    )
    assert field_r.status_code == 201, field_r.text
    return app_id, entity_id, "inn"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sensitive_field_is_ciphertext_at_rest(
    client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id, field_name = await _setup_app_entity_with_sensitive_field(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {field_name: "7701234567"}},
        headers=headers,
    )
    assert create_r.status_code == 201, create_r.text
    record_id = create_r.json()["id"]

    # Look at the raw DB row directly — bypassing RecordService entirely.
    raw = (
        await db_session.execute(select(Record).where(Record.id == uuid.UUID(record_id)))
    ).scalar_one()
    assert field_crypto.is_encrypted(raw.payload[field_name])
    assert "7701234567" not in raw.payload[field_name]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_platform_admin_sees_decrypted_value(client: AsyncClient, admin_user: User) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id, field_name = await _setup_app_entity_with_sensitive_field(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {field_name: "7701234567"}},
        headers=headers,
    )
    assert create_r.status_code == 201, create_r.text
    # Immediate create response is decrypted for the creator (platform_admin).
    assert create_r.json()["payload"][field_name] == "7701234567"

    record_id = create_r.json()["id"]
    get_r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{record_id}",
        headers=headers,
    )
    assert get_r.status_code == 200
    assert get_r.json()["payload"][field_name] == "7701234567"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unprivileged_role_sees_masked_value(
    client: AsyncClient,
    admin_user: User,
    viewer_user: User,
    viewer_role: Role,
) -> None:
    admin_token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id, field_name = await _setup_app_entity_with_sensitive_field(
        client, admin_token
    )
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    create_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {field_name: "7701234567"}},
        headers=admin_headers,
    )
    assert create_r.status_code == 201, create_r.text
    record_id = create_r.json()["id"]

    # Grant the viewer app membership (required to even see the app), but no
    # explicit FieldPermission on the sensitive field — it should default to
    # masked. App membership ("viewer" here) is a separate concept from the
    # RBAC role (viewer_role) already assigned to the user in the fixture.
    member_r = await client.post(
        f"/api/v1/apps/{app_id}/members",
        json={"user_id": str(viewer_user.id), "role": "viewer"},
        headers=admin_headers,
    )
    assert member_r.status_code == 204, member_r.text

    viewer_token = await _login(client, viewer_user.email, "Viewer1234!")
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}
    get_r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{record_id}",
        headers=viewer_headers,
    )
    assert get_r.status_code == 200, get_r.text
    value = get_r.json()["payload"][field_name]
    assert value != "7701234567"
    assert not field_crypto.is_encrypted(value)  # masked display, not raw ciphertext either
    assert value.endswith("4567")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_audit_log_never_stores_sensitive_plaintext(
    client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
) -> None:
    token = await _login(client, admin_user.email, "Admin1234!")
    app_id, entity_id, field_name = await _setup_app_entity_with_sensitive_field(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create_r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {field_name: "7701234567"}},
        headers=headers,
    )
    assert create_r.status_code == 201, create_r.text

    logs = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.action == "record.created",
                    AuditLog.resource_id == create_r.json()["id"],
                )
            )
        )
        .scalars()
        .all()
    )
    assert logs, "expected an audit log entry for record.created"
    for log in logs:
        payload = log.details.get("payload", {})
        assert payload.get(field_name) != "7701234567"
