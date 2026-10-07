"""Document registrar + номенклатура дел tests (ТЗ 3.10)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.services.registrar import RegistrarService, _format_registration_no
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------
# Unit: number formatting (pure function, no DB needed)
# ------------------------------------------------------------------


def _cfg(**kwargs) -> SimpleNamespace:
    defaults = {"prefix": "ВХ-", "suffix": "", "reset_period": "yearly", "seq_padding": 4}
    return SimpleNamespace(**{**defaults, **kwargs})


def test_format_matches_tz_example_exactly() -> None:
    # ТЗ 3.10.1's own example: «ВХ-2026/04-0001»
    assert (
        _format_registration_no(_cfg(reset_period="monthly"), "", 2026, 4, 1) == "ВХ-2026/04-0001"
    )


def test_format_yearly_has_no_month_segment() -> None:
    assert _format_registration_no(_cfg(reset_period="yearly"), "", 2026, 0, 7) == "ВХ-2026-0007"


def test_format_never_reset_has_no_date_segment() -> None:
    assert (
        _format_registration_no(
            _cfg(prefix="DOC-", reset_period="never", seq_padding=6), "", 0, 0, 42
        )
        == "DOC-000042"
    )


def test_format_includes_department_when_set() -> None:
    assert (
        _format_registration_no(_cfg(reset_period="yearly"), "FIN", 2026, 0, 3)
        == "ВХ-FIN-2026-0003"
    )


def test_format_respects_suffix_and_padding() -> None:
    cfg = _cfg(prefix="A-", suffix="-K", reset_period="never", seq_padding=2)
    assert _format_registration_no(cfg, "", 0, 0, 5) == "A-05-K"


pytestmark = pytest.mark.integration


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def admin(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "platform_admin"):
        db_session.add(Role(id="platform_admin", display_name="Platform Admin", is_system=True))
    user = User(
        email="reg_admin@example.com",
        display_name="Registrar Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    await db_session.flush()
    return user


@pytest.fixture()
async def builder(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="Builder", is_system=True))
    user = User(
        email="reg_builder@example.com",
        display_name="Builder",
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


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_app(client: AsyncClient, token: str) -> str:
    slug = f"registrar-app-{uuid.uuid4().hex[:6]}"
    r = await client.post(
        "/api/v1/apps", json={"slug": slug, "name": "Registrar Test App"}, headers=_headers(token)
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------------
# Doc type config
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_doc_type_configs_has_sane_defaults(client: AsyncClient, builder: User) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)

    resp = await client.get(f"/api/v1/apps/{app_id}/documents/doc-types", headers=_headers(token))
    assert resp.status_code == 200, resp.text
    by_type = {c["doc_type"]: c for c in resp.json()}
    assert set(by_type) == {"incoming", "outgoing", "internal"}
    assert by_type["incoming"]["prefix"] == "ВХ-"
    assert by_type["outgoing"]["prefix"] == "ИСХ-"
    assert by_type["internal"]["prefix"] == "ВН-"
    assert by_type["incoming"]["reset_period"] == "yearly"


@pytest.mark.asyncio
async def test_update_doc_type_config_forbidden_for_non_admin(
    client: AsyncClient, builder: User
) -> None:
    token = await _login(client, builder.email, "Build1234!")
    app_id = await _create_app(client, token)
    resp = await client.put(
        f"/api/v1/apps/{app_id}/documents/doc-types/incoming",
        json={"prefix": "X-"},
        headers=_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_doc_type_config_unknown_type_404(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    resp = await client.put(
        f"/api/v1/apps/{app_id}/documents/doc-types/bogus",
        json={"prefix": "X-"},
        headers=_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_can_update_doc_type_config(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    resp = await client.put(
        f"/api/v1/apps/{app_id}/documents/doc-types/incoming",
        json={
            "prefix": "IN-",
            "reset_period": "monthly",
            "include_department": True,
            "seq_padding": 5,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["prefix"] == "IN-"
    assert data["reset_period"] == "monthly"
    assert data["include_department"] is True
    assert data["seq_padding"] == 5


# ------------------------------------------------------------------
# Registration numbering
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_document_generates_sequential_numbers(
    client: AsyncClient, admin: User
) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    entity_id, record_id = str(uuid.uuid4()), str(uuid.uuid4())

    r1 = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={"entity_id": entity_id, "record_id": record_id, "doc_type": "incoming"},
        headers=_headers(token),
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={"entity_id": entity_id, "record_id": str(uuid.uuid4()), "doc_type": "incoming"},
        headers=_headers(token),
    )
    assert r2.status_code == 201, r2.text

    no1, no2 = r1.json()["registration_no"], r2.json()["registration_no"]
    assert no1 != no2
    assert no1.startswith("ВХ-")
    # Sequential: extract the trailing digits and confirm they're consecutive.
    seq1, seq2 = int(no1.rsplit("-", 1)[1]), int(no2.rsplit("-", 1)[1])
    assert seq2 == seq1 + 1


@pytest.mark.asyncio
async def test_doc_types_have_independent_counters(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    entity_id = str(uuid.uuid4())

    incoming = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={"entity_id": entity_id, "record_id": str(uuid.uuid4()), "doc_type": "incoming"},
        headers=_headers(token),
    )
    outgoing = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={"entity_id": entity_id, "record_id": str(uuid.uuid4()), "doc_type": "outgoing"},
        headers=_headers(token),
    )
    # Both are the first document of their type — both get seq 1, just with
    # different prefixes, proving the counters don't share state.
    assert incoming.json()["registration_no"].endswith("-0001")
    assert outgoing.json()["registration_no"].endswith("-0001")
    assert incoming.json()["registration_no"] != outgoing.json()["registration_no"]


@pytest.mark.asyncio
async def test_departments_have_independent_counters_when_enabled(
    client: AsyncClient, admin: User
) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    await client.put(
        f"/api/v1/apps/{app_id}/documents/doc-types/internal",
        json={"include_department": True},
        headers=_headers(token),
    )
    entity_id = str(uuid.uuid4())

    fin = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={
            "entity_id": entity_id,
            "record_id": str(uuid.uuid4()),
            "doc_type": "internal",
            "department_code": "FIN",
        },
        headers=_headers(token),
    )
    hr = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={
            "entity_id": entity_id,
            "record_id": str(uuid.uuid4()),
            "doc_type": "internal",
            "department_code": "HR",
        },
        headers=_headers(token),
    )
    assert fin.json()["registration_no"].endswith("-0001")
    assert hr.json()["registration_no"].endswith("-0001")
    assert "FIN" in fin.json()["registration_no"]
    assert "HR" in hr.json()["registration_no"]

    fin2 = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={
            "entity_id": entity_id,
            "record_id": str(uuid.uuid4()),
            "doc_type": "internal",
            "department_code": "FIN",
        },
        headers=_headers(token),
    )
    assert fin2.json()["registration_no"].endswith(
        "-0002"
    )  # FIN's own counter advanced, HR's didn't


@pytest.mark.asyncio
async def test_registration_conflict_returns_409(
    client: AsyncClient, admin: User, db_session: AsyncSession
) -> None:
    """Pre-seed the number the atomic counter is about to produce, to force
    the IntegrityError → RegistrationConflictError path."""
    from app.models.documents import DocumentRegistration

    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    app_uuid = uuid.UUID(app_id)

    db_session.add(
        DocumentRegistration(
            app_id=app_uuid,
            entity_id=uuid.uuid4(),
            record_id=uuid.uuid4(),
            doc_type="incoming",
            registration_no=f"ВХ-{datetime.now().year}-0001",
        )
    )
    await db_session.flush()

    resp = await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={
            "entity_id": str(uuid.uuid4()),
            "record_id": str(uuid.uuid4()),
            "doc_type": "incoming",
        },
        headers=_headers(token),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_registrations_filters_by_doc_type(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    entity_id = str(uuid.uuid4())
    await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={"entity_id": entity_id, "record_id": str(uuid.uuid4()), "doc_type": "incoming"},
        headers=_headers(token),
    )
    await client.post(
        f"/api/v1/apps/{app_id}/documents/register",
        json={"entity_id": entity_id, "record_id": str(uuid.uuid4()), "doc_type": "outgoing"},
        headers=_headers(token),
    )

    resp = await client.get(
        f"/api/v1/apps/{app_id}/documents/registrations?doc_type=incoming",
        headers=_headers(token),
    )
    assert resp.status_code == 200
    assert all(r["doc_type"] == "incoming" for r in resp.json())
    assert len(resp.json()) == 1


# ------------------------------------------------------------------
# Filing cases
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_list_filing_case(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)

    resp = await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={
            "index_code": "01-05",
            "title": "Приказы по основной деятельности",
            "retention_years": 5,
        },
        headers=_headers(token),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "open"

    list_resp = await client.get(
        f"/api/v1/apps/{app_id}/documents/filing-cases", headers=_headers(token)
    )
    assert len(list_resp.json()) == 1


@pytest.mark.asyncio
async def test_create_child_filing_case_under_existing_parent(
    client: AsyncClient, admin: User
) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    parent = await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={"index_code": "01", "title": "Root"},
        headers=_headers(token),
    )
    parent_id = parent.json()["id"]

    child = await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={"index_code": "01-01", "title": "Child", "parent_id": parent_id},
        headers=_headers(token),
    )
    assert child.status_code == 201, child.text
    assert child.json()["parent_id"] == parent_id


@pytest.mark.asyncio
async def test_create_filing_case_with_unknown_parent_404(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    resp = await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={"index_code": "02", "title": "X", "parent_id": str(uuid.uuid4())},
        headers=_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_filing_case_to_closed_sets_closed_at(
    client: AsyncClient, admin: User
) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    create = await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={"index_code": "03", "title": "To close"},
        headers=_headers(token),
    )
    case_id = create.json()["id"]

    resp = await client.patch(
        f"/api/v1/apps/{app_id}/documents/filing-cases/{case_id}",
        json={"status": "closed"},
        headers=_headers(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"
    assert resp.json()["closed_at"] is not None


@pytest.mark.asyncio
async def test_delete_filing_case(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    create = await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={"index_code": "04", "title": "To delete"},
        headers=_headers(token),
    )
    case_id = create.json()["id"]

    resp = await client.delete(
        f"/api/v1/apps/{app_id}/documents/filing-cases/{case_id}", headers=_headers(token)
    )
    assert resp.status_code == 204

    list_resp = await client.get(
        f"/api/v1/apps/{app_id}/documents/filing-cases", headers=_headers(token)
    )
    assert list_resp.json() == []


@pytest.mark.asyncio
async def test_export_filing_cases_csv(client: AsyncClient, admin: User) -> None:
    token = await _login(client, admin.email, "Admin1234!")
    app_id = await _create_app(client, token)
    await client.post(
        f"/api/v1/apps/{app_id}/documents/filing-cases",
        json={"index_code": "05", "title": "Exportable"},
        headers=_headers(token),
    )

    resp = await client.get(
        f"/api/v1/apps/{app_id}/documents/filing-cases/export?format=csv", headers=_headers(token)
    )
    assert resp.status_code == 200
    assert b"Exportable" in resp.content


# ------------------------------------------------------------------
# Auto-closure (service-level — the worker task is just a thin wrapper)
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_close_overdue_cases_closes_only_past_due_open_cases(
    db_session: AsyncSession,
) -> None:
    from app.models.documents import FilingCase

    app_id = uuid.uuid4()
    overdue = FilingCase(
        app_id=app_id, index_code="A", title="Overdue", close_by=date.today() - timedelta(days=1)
    )
    not_yet = FilingCase(
        app_id=app_id, index_code="B", title="Not yet", close_by=date.today() + timedelta(days=30)
    )
    already_closed = FilingCase(
        app_id=app_id,
        index_code="C",
        title="Already closed",
        status="closed",
        close_by=date.today() - timedelta(days=1),
    )
    db_session.add_all([overdue, not_yet, already_closed])
    await db_session.flush()

    closed = await RegistrarService(db_session).close_overdue_cases()

    assert {c.index_code for c in closed} == {"A"}
    assert overdue.status == "closed"
    assert overdue.closed_at is not None
    assert not_yet.status == "open"
