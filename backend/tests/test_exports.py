"""Tests for GET /export — XLSX, CSV, PDF export endpoint."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.exports import ExportService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id, display in [("app_builder", "Builder")]:
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name=display, is_system=True))
    user = User(
        email="export_builder@example.com",
        display_name="Export Builder",
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


async def _setup_entity(client: AsyncClient, token: str) -> tuple[str, str]:
    slug = f"export-app-{uuid.uuid4().hex[:6]}"
    app_r = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Export Test App"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert app_r.status_code == 201, app_r.text
    app_id = app_r.json()["id"]
    entity_r = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "orders", "display_name": "Orders"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert entity_r.status_code == 201, entity_r.text
    return app_id, entity_r.json()["id"]


async def _create_record(
    client: AsyncClient, token: str, app_id: str, entity_id: str, payload: dict
) -> dict:
    r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": payload},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _create_field(
    client: AsyncClient, token: str, app_id: str, entity_id: str, name: str, field_type: str
) -> None:
    r = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": name, "display_name": name, "field_type": field_type},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text


# ------------------------------------------------------------------
# Unit tests — ExportService in isolation
# ------------------------------------------------------------------


def test_to_csv_produces_utf8_bom_bytes() -> None:
    headers = ["name", "age"]
    rows = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    csv_bytes = ExportService._to_csv(headers, rows)
    assert isinstance(csv_bytes, bytes)
    assert csv_bytes.startswith(b"\xef\xbb\xbf"), "expected UTF-8 BOM"
    text = csv_bytes.decode("utf-8-sig")
    assert "name,age" in text
    assert "Alice" in text
    assert "Bob" in text


def test_to_csv_empty_rows() -> None:
    csv_bytes = ExportService._to_csv([], [])
    assert isinstance(csv_bytes, bytes)


def test_to_xlsx_produces_xlsx_magic() -> None:
    headers = ["title", "count"]
    rows = [{"title": "Widget", "count": 5}]
    xlsx_bytes = ExportService._to_xlsx(headers, rows)
    # XLSX is a ZIP; magic bytes are PK\x03\x04
    assert xlsx_bytes[:4] == b"PK\x03\x04"


def test_to_xlsx_handles_nested_values() -> None:
    headers = ["tags"]
    rows = [{"tags": ["a", "b"]}]
    xlsx_bytes = ExportService._to_xlsx(headers, rows)
    assert xlsx_bytes[:4] == b"PK\x03\x04"


def test_to_pdf_produces_pdf_header() -> None:
    headers = ["item", "qty"]
    rows = [{"item": "Widget", "qty": 3}]
    pdf_bytes = ExportService._to_pdf(headers, rows)
    assert pdf_bytes.startswith(b"%PDF-")


# ------------------------------------------------------------------
# Integration tests — GET /export via HTTP
# ------------------------------------------------------------------


@pytest.mark.anyio
async def test_export_xlsx_returns_file(client: AsyncClient, builder: User) -> None:
    token = await _login(client, "export_builder@example.com", "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    await _create_field(client, token, app_id, entity_id, "name", "text")
    await _create_field(client, token, app_id, entity_id, "age", "number")
    await _create_record(client, token, app_id, entity_id, {"name": "Alice", "age": 30})

    r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/export",
        params={"format": "xlsx"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "Content-Disposition" in r.headers
    assert r.content[:4] == b"PK\x03\x04"


@pytest.mark.anyio
async def test_export_csv_returns_file(client: AsyncClient, builder: User) -> None:
    token = await _login(client, "export_builder@example.com", "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    await _create_field(client, token, app_id, entity_id, "name", "text")
    await _create_field(client, token, app_id, entity_id, "score", "number")
    await _create_record(client, token, app_id, entity_id, {"name": "Bob", "score": 99})

    r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/export",
        params={"format": "csv"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    text = r.content.decode("utf-8-sig")
    assert "name" in text
    assert "Bob" in text


@pytest.mark.anyio
async def test_export_pdf_returns_file(client: AsyncClient, builder: User) -> None:
    token = await _login(client, "export_builder@example.com", "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    await _create_field(client, token, app_id, entity_id, "title", "text")
    await _create_record(client, token, app_id, entity_id, {"title": "Report"})

    r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/export",
        params={"format": "pdf"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")


@pytest.mark.anyio
async def test_export_empty_entity_returns_empty_file(client: AsyncClient, builder: User) -> None:
    token = await _login(client, "export_builder@example.com", "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)

    r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/export",
        params={"format": "csv"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    # No rows — just BOM or empty
    assert isinstance(r.content, bytes)


@pytest.mark.anyio
async def test_export_invalid_format_rejected(client: AsyncClient, builder: User) -> None:
    token = await _login(client, "export_builder@example.com", "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)

    r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/export",
        params={"format": "docx"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.anyio
async def test_export_requires_auth(client: AsyncClient, builder: User) -> None:
    token = await _login(client, "export_builder@example.com", "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)

    r = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/export",
        params={"format": "xlsx"},
    )
    assert r.status_code == 401
