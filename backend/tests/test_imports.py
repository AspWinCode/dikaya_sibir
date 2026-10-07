"""
Import (CSV/XLSX) tests.

Unit tests: parser logic (pure, no DB).
Integration tests: POST /import endpoint creates records via RecordService.
"""

from __future__ import annotations

import io
import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.imports import ImportService, ImportValidationError
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    for role_id in ("app_builder",):
        if not await db_session.get(Role, role_id):
            db_session.add(Role(id=role_id, display_name="App Builder", is_system=True))
    user = User(
        email="import_builder@example.com",
        display_name="Import Builder",
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
    slug = f"import-app-{uuid.uuid4().hex[:6]}"
    headers = {"Authorization": f"Bearer {token}"}
    app = await client.post(
        "/api/v1/apps",
        json={"slug": slug, "name": "Import Test App"},
        headers=headers,
    )
    app_id = app.json()["id"]
    entity = await client.post(
        f"/api/v1/apps/{app_id}/entities",
        json={"slug": "contacts", "display_name": "Contacts"},
        headers=headers,
    )
    entity_id = entity.json()["id"]
    for name, field_type in [("name", "text"), ("score", "number")]:
        r = await client.post(
            f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
            json={"name": name, "display_name": name, "field_type": field_type},
            headers=headers,
        )
        assert r.status_code == 201, r.text
    return app_id, entity_id


# ------------------------------------------------------------------
# Unit: CSV parser
# ------------------------------------------------------------------


class TestCsvParser:
    def _svc(self) -> ImportService:
        return ImportService(None)  # type: ignore[arg-type]  # no DB needed for pure parse

    def test_basic_csv(self) -> None:
        csv_data = b"name,email\nAlice,alice@example.com\nBob,bob@example.com\n"
        rows = self._svc()._parse_csv(csv_data)
        assert len(rows) == 2
        assert rows[0] == {"name": "Alice", "email": "alice@example.com"}
        assert rows[1] == {"name": "Bob", "email": "bob@example.com"}

    def test_csv_with_bom(self) -> None:
        # .encode("utf-8-sig") already prepends the BOM bytes - the source string
        # itself must NOT also contain a literal ﻿, or the decode step (which
        # strips exactly one leading BOM) leaves the second one stuck to the header.
        csv_data = "name,email\nAlice,a@b.com\n".encode("utf-8-sig")
        rows = self._svc()._parse_csv(csv_data)
        assert rows[0]["name"] == "Alice"

    def test_empty_csv_returns_empty(self) -> None:
        csv_data = b"name,email\n"
        rows = self._svc()._parse_csv(csv_data)
        assert rows == []

    def test_csv_only_header_returns_empty(self) -> None:
        csv_data = b"col1,col2\n"
        rows = self._svc()._parse_csv(csv_data)
        assert rows == []


# ------------------------------------------------------------------
# Unit: unsupported file type raises ImportValidationError
# ------------------------------------------------------------------


class TestUnsupportedType:
    @pytest.mark.asyncio
    async def test_unsupported_extension_raises(self, db_session: AsyncSession) -> None:
        svc = ImportService(db_session)
        with pytest.raises(ImportValidationError, match="Unsupported file type"):
            await svc.import_records(
                uuid.uuid4(),
                uuid.uuid4(),
                b"some data",
                "file.pdf",
            )


# ------------------------------------------------------------------
# Unit: ImportService with mocked RecordService
# ------------------------------------------------------------------


class TestImportServiceUnit:
    @pytest.mark.asyncio
    async def test_skips_empty_rows(self, db_session: AsyncSession) -> None:
        # One comma per header column (2 headers -> 1 comma) so csv.DictReader
        # doesn't spill a third value into its `None` restkey - a row shaped
        # like that isn't "empty", it's malformed, and correctly becomes an
        # error rather than a skip.
        csv_data = b"name,email\n,\n"
        svc = ImportService(db_session)
        result = await svc.import_records(uuid.uuid4(), uuid.uuid4(), csv_data, "data.csv")
        assert result.total == 1
        assert result.skipped == 1
        assert result.created == 0

    @pytest.mark.asyncio
    async def test_column_map_applied(self, db_session: AsyncSession) -> None:
        """column_map remaps CSV headers to entity field names."""
        csv_data = b"Full Name,E-mail\nAlice,alice@example.com\n"
        svc = ImportService(db_session)
        # The entity doesn't exist → RecordService will fail validation, we check error row
        result = await svc.import_records(
            uuid.uuid4(),
            uuid.uuid4(),
            csv_data,
            "data.csv",
            column_map={"Full Name": "name", "E-mail": "email"},
        )
        # total=1, created=0 (entity not in DB → error), errors has the row
        assert result.total == 1
        if result.errors:
            assert result.errors[0]["row"] == 2


# ------------------------------------------------------------------
# Integration: POST /import endpoint
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_csv_creates_records(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    csv_content = b"name,score\nAlice,90\nBob,85\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    assert data["created"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == []

    # Verify records actually exist
    list_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        headers=headers,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    names = [r["payload"]["name"] for r in items]
    assert "Alice" in names
    assert "Bob" in names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_csv_with_column_map(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    import json

    csv_content = b"Full Name,Score\nCarol,95\n"
    column_map = json.dumps({"Full Name": "name", "Score": "score"})

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("contacts.csv", io.BytesIO(csv_content), "text/csv")},
        params={"column_map": column_map},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created"] == 1

    list_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        headers=headers,
    )
    record = list_resp.json()["items"][0]["payload"]
    assert record["name"] == "Carol"
    assert record["score"] == "95"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_unsupported_type_returns_400(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_invalid_column_map_returns_422(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        params={"column_map": "not-valid-json"},
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_returns_row_errors_for_invalid_rows(
    client: AsyncClient, builder: User
) -> None:
    """Rows that fail entity validation are reported in errors, not abort the batch."""
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    # Add a required field to the entity
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "email", "display_name": "Email", "field_type": "email", "is_required": True},
        headers=headers,
    )

    # Row 2 is valid (has email), row 3 is missing required email field
    csv_content = b"name,email\nAlice,alice@example.com\nBob,\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    # Alice succeeds, Bob's empty email → validation error (required field missing or empty string)
    assert data["created"] >= 1
    # At least one row should be reported as error or skipped (empty string → skipped by import)
    assert data["created"] + data["skipped"] + len(data["errors"]) == data["total"]


# ------------------------------------------------------------------
# Unit: file size / row count limits (ТЗ Приложение A)
# ------------------------------------------------------------------


class TestImportLimits:
    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self, monkeypatch) -> None:
        # Both checks below raise before any DB access, so — like TestCsvParser
        # — a real session isn't needed.
        import app.services.imports as imports_module

        monkeypatch.setattr(
            imports_module, "MAX_IMPORT_FILE_SIZE", 10
        )  # 10 bytes, avoids allocating 50MB in a test

        svc = ImportService(None)  # type: ignore[arg-type]
        with pytest.raises(ImportValidationError, match="exceeds the maximum import size"):
            await svc.import_records(
                uuid.uuid4(), uuid.uuid4(), b"name,email\nAlice,a@b.com\n", "data.csv"
            )

    @pytest.mark.asyncio
    async def test_row_count_over_limit_rejected(self, monkeypatch) -> None:
        import app.services.imports as imports_module

        monkeypatch.setattr(imports_module, "MAX_IMPORT_ROWS", 2)

        csv_content = b"name\nA\nB\nC\n"  # 3 rows > limit of 2
        svc = ImportService(None)  # type: ignore[arg-type]
        with pytest.raises(ImportValidationError, match="exceeding the limit of 2"):
            await svc.import_records(uuid.uuid4(), uuid.uuid4(), csv_content, "data.csv")

    @pytest.mark.asyncio
    async def test_row_count_at_limit_is_allowed(
        self, db_session: AsyncSession, monkeypatch
    ) -> None:
        import app.services.imports as imports_module

        monkeypatch.setattr(imports_module, "MAX_IMPORT_ROWS", 2)

        csv_content = b"name\nA\nB\n"  # exactly 2 rows == limit
        svc = ImportService(db_session)
        # Entity doesn't exist, so rows will error out individually — the
        # point here is only that the *limit* itself doesn't reject it.
        result = await svc.import_records(uuid.uuid4(), uuid.uuid4(), csv_content, "data.csv")
        assert result.total == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_file_size_limit_returns_400(
    client: AsyncClient, builder: User, monkeypatch
) -> None:
    import app.services.imports as imports_module

    monkeypatch.setattr(imports_module, "MAX_IMPORT_FILE_SIZE", 10)

    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(b"name,score\nAlice,90\n"), "text/csv")},
    )
    assert resp.status_code == 400
    assert "maximum import size" in resp.json()["detail"]


# ------------------------------------------------------------------
# Integration: on_error="abort" (ТЗ 3.8 — "отменить весь импорт")
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_abort_mode_rolls_back_valid_rows_when_one_fails(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/fields",
        json={"name": "email", "display_name": "Email", "field_type": "email", "is_required": True},
        headers=headers,
    )

    # Alice is valid; Bob is missing the required email → should fail the whole import.
    csv_content = b"name,email\nAlice,alice@example.com\nBob,\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
        params={"on_error": "abort"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["aborted"] is True
    assert data["created"] == 0
    assert len(data["errors"]) >= 1

    # Nothing was actually persisted — not even Alice, who was individually valid.
    list_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        headers=headers,
    )
    assert list_resp.json()["items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_abort_mode_succeeds_when_all_rows_are_valid(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    csv_content = b"name,score\nAlice,90\nBob,85\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
        params={"on_error": "abort"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["aborted"] is False
    assert data["created"] == 2


# ------------------------------------------------------------------
# Integration: key_field upsert (ТЗ 3.8 — обновление по ключевому полю)
# ------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_updates_existing_record_by_key(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"name": "Alice", "score": "10"}},
        headers=headers,
    )
    rec_id = create.json()["id"]

    csv_content = b"name,score\nAlice,99\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
        params={"key_field": "name"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created"] == 0
    assert data["updated"] == 1

    get_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}",
        headers=headers,
    )
    assert get_resp.json()["payload"]["score"] == "99"

    # No duplicate was created alongside the update.
    list_resp = await client.get(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        headers=headers,
    )
    assert len(list_resp.json()["items"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_creates_when_no_existing_match(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    csv_content = b"name,score\nCarol,77\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
        params={"key_field": "name"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["created"] == 1
    assert data["updated"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_upsert_does_not_match_soft_deleted_records(
    client: AsyncClient, builder: User
) -> None:
    """A key match against a soft-deleted record should create a new record,
    not resurrect/overwrite the deleted one."""
    token = await _login(client, builder.email, "Build1234!")
    app_id, entity_id = await _setup_entity(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    create = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records",
        json={"payload": {"name": "Dave", "score": "10"}},
        headers=headers,
    )
    rec_id = create.json()["id"]
    await client.delete(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/{rec_id}",
        headers=headers,
    )

    csv_content = b"name,score\nDave,50\n"
    resp = await client.post(
        f"/api/v1/apps/{app_id}/entities/{entity_id}/records/import",
        headers=headers,
        files={"file": ("data.csv", io.BytesIO(csv_content), "text/csv")},
        params={"key_field": "name"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] == 1
    assert resp.json()["updated"] == 0
