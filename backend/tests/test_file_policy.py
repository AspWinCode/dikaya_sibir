"""FilePolicy tests: admin-configurable size/format/count limits.

GET/PUT /auth/file-policy only touch the DB (no S3/ClamAV), so — unlike
test_files.py — these run as real HTTP integration tests.
"""

import uuid

import pytest
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.schemas.auth import FilePolicyUpdate
from app.services.file_policy import DEFAULT_ALLOWED_EXTENSIONS, FilePolicyService
from app.services.files import FileError, FileService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_files import FakeAntivirus, FakeStorage, FakeUploadFile

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
async def admin(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "platform_admin"):
        db_session.add(Role(id="platform_admin", display_name="Platform Admin", is_system=True))
    user = User(
        email="filepolicy_admin@example.com",
        display_name="File Policy Admin",
        password_hash=hash_password("Admin1234!"),
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id="platform_admin"))
    await db_session.flush()
    return user


@pytest.fixture()
async def regular_user(db_session: AsyncSession) -> User:
    if not await db_session.get(Role, "app_builder"):
        db_session.add(Role(id="app_builder", display_name="Builder", is_system=True))
    user = User(
        email="filepolicy_user@example.com",
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


def _ids() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


# ------------------------------------------------------------------
# API: GET/PUT /auth/file-policy
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_file_policy_returns_defaults(client: AsyncClient) -> None:
    r = await client.get("/api/v1/auth/file-policy")
    assert r.status_code == 200
    data = r.json()
    assert data["max_file_size_mb"] == 100
    assert data["max_files_per_record"] == 50
    assert set(data["allowed_extensions"]) == set(DEFAULT_ALLOWED_EXTENSIONS)


@pytest.mark.asyncio
async def test_update_file_policy_requires_auth(client: AsyncClient) -> None:
    r = await client.put("/api/v1/auth/file-policy", json={"max_file_size_mb": 50})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_update_file_policy_forbidden_for_regular_user(
    client: AsyncClient, regular_user: User
) -> None:
    token = await _login(client, "filepolicy_user@example.com", "User1234!")
    r = await client.put(
        "/api/v1/auth/file-policy",
        json={"max_file_size_mb": 50},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_file_policy(client: AsyncClient, admin: User) -> None:
    token = await _login(client, "filepolicy_admin@example.com", "Admin1234!")
    r = await client.put(
        "/api/v1/auth/file-policy",
        json={"max_file_size_mb": 250, "max_files_per_record": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["max_file_size_mb"] == 250
    assert data["max_files_per_record"] == 10
    # Untouched field keeps its previous value.
    assert set(data["allowed_extensions"]) == set(DEFAULT_ALLOWED_EXTENSIONS)


@pytest.mark.asyncio
async def test_update_file_policy_rejects_out_of_range_size(
    client: AsyncClient, admin: User
) -> None:
    token = await _login(client, "filepolicy_admin@example.com", "Admin1234!")
    r = await client.put(
        "/api/v1/auth/file-policy",
        json={"max_file_size_mb": 600},  # ТЗ range is 1-500
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_file_policy_rejects_empty_extension_list(
    client: AsyncClient, admin: User
) -> None:
    token = await _login(client, "filepolicy_admin@example.com", "Admin1234!")
    r = await client.put(
        "/api/v1/auth/file-policy",
        json={"allowed_extensions": []},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_file_policy_normalizes_extensions(client: AsyncClient, admin: User) -> None:
    token = await _login(client, "filepolicy_admin@example.com", "Admin1234!")
    r = await client.put(
        "/api/v1/auth/file-policy",
        json={"allowed_extensions": [".PDF", "  MP4 ", "pdf"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert sorted(r.json()["allowed_extensions"]) == ["mp4", "pdf"]


# ------------------------------------------------------------------
# FileService respects the policy
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_service_uses_custom_max_size(db_session: AsyncSession) -> None:
    await FilePolicyService(db_session).update(FilePolicyUpdate(max_file_size_mb=1))
    svc = FileService(db_session, FakeStorage(), FakeAntivirus())
    app_id, entity_id, record_id = _ids()

    oversized = b"x" * (2 * 1024 * 1024)  # 2 MB > custom 1 MB cap
    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(
            app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", oversized)
        )
    assert "1 MB" in exc_info.value.detail


@pytest.mark.asyncio
async def test_file_service_allows_extension_added_by_admin(db_session: AsyncSession) -> None:
    await FilePolicyService(db_session).update(
        FilePolicyUpdate(allowed_extensions=[*DEFAULT_ALLOWED_EXTENSIONS, "mp4"])
    )
    svc = FileService(db_session, FakeStorage(), FakeAntivirus())
    app_id, entity_id, record_id = _ids()

    result = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("clip.mp4", b"data")
    )
    assert result.original_filename == "clip.mp4"


@pytest.mark.asyncio
async def test_file_service_enforces_max_files_per_record(db_session: AsyncSession) -> None:
    await FilePolicyService(db_session).update(FilePolicyUpdate(max_files_per_record=2))
    svc = FileService(db_session, FakeStorage(), FakeAntivirus())
    app_id, entity_id, record_id = _ids()

    await svc.upload_file(app_id, entity_id, record_id, "attachment", FakeUploadFile("a.pdf", b"a"))
    await svc.upload_file(app_id, entity_id, record_id, "attachment", FakeUploadFile("b.pdf", b"b"))

    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(
            app_id, entity_id, record_id, "attachment", FakeUploadFile("c.pdf", b"c")
        )
    assert "maximum of 2 files" in exc_info.value.detail


@pytest.mark.asyncio
async def test_replace_at_the_ceiling_does_not_trip_the_limit(db_session: AsyncSession) -> None:
    """A replace supersedes one file and adds one — net count is unchanged,
    so it must be allowed even when the record is already at the ceiling."""
    await FilePolicyService(db_session).update(FilePolicyUpdate(max_files_per_record=1))
    svc = FileService(db_session, FakeStorage(), FakeAntivirus())
    app_id, entity_id, record_id = _ids()

    await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("a.pdf", b"a"), replace=True
    )
    # Should not raise even though the record already has 1 file (== ceiling).
    result = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("a2.pdf", b"a2"), replace=True
    )
    assert result.version == 2


@pytest.mark.asyncio
async def test_max_files_override_can_only_tighten_not_loosen(db_session: AsyncSession) -> None:
    """Policy ceiling is 2; a block passing max_files=10 must NOT be able to
    raise the effective limit above the platform ceiling."""
    await FilePolicyService(db_session).update(FilePolicyUpdate(max_files_per_record=2))
    svc = FileService(db_session, FakeStorage(), FakeAntivirus())
    app_id, entity_id, record_id = _ids()

    await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("a.pdf", b"a"), max_files=10
    )
    await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("b.pdf", b"b"), max_files=10
    )

    with pytest.raises(FileError):
        await svc.upload_file(
            app_id, entity_id, record_id, "attachment", FakeUploadFile("c.pdf", b"c"), max_files=10
        )


@pytest.mark.asyncio
async def test_max_files_override_can_tighten_below_ceiling(db_session: AsyncSession) -> None:
    """Policy ceiling is 5; a block passing max_files=1 enforces the tighter
    limit."""
    await FilePolicyService(db_session).update(FilePolicyUpdate(max_files_per_record=5))
    svc = FileService(db_session, FakeStorage(), FakeAntivirus())
    app_id, entity_id, record_id = _ids()

    await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("a.pdf", b"a"), max_files=1
    )

    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(
            app_id, entity_id, record_id, "attachment", FakeUploadFile("b.pdf", b"b"), max_files=1
        )
    assert "maximum of 1 files" in exc_info.value.detail
