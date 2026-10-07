"""FileService tests: upload/scan/reject, presigned download, and version chains.

Runs against the FileService directly with fake S3/ClamAV clients — CI has no
MinIO/ClamAV containers (see .github/workflows/ci.yml), so hitting the real
HTTP endpoints would require services that aren't provisioned there.
"""

import uuid

import pytest
from app.services.files import FileError, FileService, RecordFileNotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration  # exercises FileService against the real test DB


class FakeUploadFile:
    """Minimal stand-in for fastapi.UploadFile."""

    def __init__(self, filename: str, data: bytes, content_type: str = "text/plain") -> None:
        self.filename = filename
        self.content_type = content_type
        self._data = data

    async def read(self) -> bytes:
        return self._data


class FakeAntivirus:
    """Always-clean by default; set `infected=True` to simulate a hit."""

    def __init__(self, infected: bool = False) -> None:
        self.infected = infected
        self.scanned: list[bytes] = []

    async def scan_bytes(self, data: bytes) -> tuple[bool, str]:
        self.scanned.append(data)
        if self.infected:
            return False, "stream: Eicar-Test-Signature FOUND"
        return True, "stream: OK"


class FakeStorage:
    """In-memory S3 substitute that records calls for assertions."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    @staticmethod
    def make_key(
        app_id: uuid.UUID, entity_id: uuid.UUID, record_id: uuid.UUID, filename: str
    ) -> str:
        safe = filename.replace("/", "_").replace("..", "_")
        return f"files/{app_id}/{entity_id}/{record_id}/{uuid.uuid4()}_{safe}"

    async def upload(
        self, bucket, key, data, content_type="application/octet-stream", metadata=None
    ) -> None:
        self.objects[key] = data

    async def get_presigned_url(self, bucket, key, expires=3600, filename=None) -> str:
        return f"https://fake-s3.local/{bucket}/{key}?expires={expires}"

    async def delete(self, bucket, key) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)


@pytest.fixture()
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture()
def av() -> FakeAntivirus:
    return FakeAntivirus()


@pytest.fixture()
def svc(db_session: AsyncSession, storage: FakeStorage, av: FakeAntivirus) -> FileService:
    # FileService.make_key is invoked as S3Storage.make_key (a staticmethod on
    # the real class) inside upload_file, so we patch it to use our fake's key
    # scheme is irrelevant — but the real S3Storage class method is stateless
    # and safe to call as-is; only .upload/.delete/.get_presigned_url need faking.
    return FileService(db_session, storage, av)


def _ids() -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


# ------------------------------------------------------------------
# Upload: validation
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_creates_version_1(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    upload = FakeUploadFile("contract.pdf", b"hello world")

    result = await svc.upload_file(app_id, entity_id, record_id, "attachment", upload)

    assert result.version == 1
    assert result.is_latest is True
    assert result.previous_version_id is None
    assert result.original_filename == "contract.pdf"
    assert result.size_bytes == len(b"hello world")


@pytest.mark.asyncio
async def test_upload_rejects_extension_not_on_whitelist(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    upload = FakeUploadFile("payload.exe", b"MZ...")

    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(app_id, entity_id, record_id, "attachment", upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_extensionless_file(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    upload = FakeUploadFile("README", b"no extension")

    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(app_id, entity_id, record_id, "attachment", upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    # .pdf is on the default whitelist, so this exercises the size check
    # specifically rather than the extension check.
    oversized = b"x" * (100 * 1024 * 1024 + 1)
    upload = FakeUploadFile("big.pdf", oversized)

    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(app_id, entity_id, record_id, "attachment", upload)
    assert exc_info.value.status_code == 400
    assert "100 MB" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_rejects_infected_file(db_session: AsyncSession, storage: FakeStorage) -> None:
    infected_av = FakeAntivirus(infected=True)
    svc = FileService(db_session, storage, infected_av)
    app_id, entity_id, record_id = _ids()
    upload = FakeUploadFile("eicar.txt", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE")

    with pytest.raises(FileError) as exc_info:
        await svc.upload_file(app_id, entity_id, record_id, "attachment", upload)
    assert exc_info.value.status_code == 422
    # Infected payload must never reach storage.
    assert storage.objects == {}


# ------------------------------------------------------------------
# Versioning — replace=False (default): every upload is independent.
# This is the multi-file-attachment shape (RuntimeApp's FileUploadBlock with
# multiple=True): several files coexist under the same field_name, even if
# they happen to share a filename.
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_replace_same_filename_stays_independent(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()

    a = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"a")
    )
    b = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"b")
    )

    assert a.version == 1 and b.version == 1
    assert a.previous_version_id is None and b.previous_version_id is None
    assert a.is_latest is True and b.is_latest is True

    files = await svc.list_files(record_id)
    assert {f.id for f in files} == {a.id, b.id}  # both coexist, neither superseded


@pytest.mark.asyncio
async def test_without_replace_different_filename_stays_independent(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()

    a = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("a.pdf", b"a")
    )
    b = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("b.pdf", b"b")
    )

    assert a.version == 1 and b.version == 1
    files = await svc.list_files(record_id)
    assert {f.id for f in files} == {a.id, b.id}


# ------------------------------------------------------------------
# Versioning — replace=True: every upload supersedes the field's current
# file. This is the single-value shape (DatabasePage's FileCell "Заменить").
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_same_filename_creates_new_version(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()

    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"v1"), replace=True
    )
    v2 = await svc.upload_file(
        app_id,
        entity_id,
        record_id,
        "attachment",
        FakeUploadFile("doc.pdf", b"v2 longer"),
        replace=True,
    )

    assert v2.version == 2
    assert v2.previous_version_id == v1.id
    assert v2.is_latest is True

    files = await svc.list_files(record_id)
    assert [f.id for f in files] == [v2.id]  # only the latest shows by default


@pytest.mark.asyncio
async def test_replace_different_filename_still_versions(svc: FileService) -> None:
    """Replacing 'scan.pdf' with 'scan_v2.pdf' is still a new version of the
    same field — replace is keyed on (record, field), not the filename."""
    app_id, entity_id, record_id = _ids()

    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("scan.pdf", b"1"), replace=True
    )
    v2 = await svc.upload_file(
        app_id,
        entity_id,
        record_id,
        "attachment",
        FakeUploadFile("scan_v2.pdf", b"2"),
        replace=True,
    )

    assert v2.version == 2
    assert v2.previous_version_id == v1.id

    files = await svc.list_files(record_id)
    assert [f.id for f in files] == [v2.id]


@pytest.mark.asyncio
async def test_replace_marks_previous_version_not_latest(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()

    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"v1"), replace=True
    )
    await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"v2"), replace=True
    )

    all_files = await svc.list_files(record_id, include_all_versions=True)
    by_id = {f.id: f for f in all_files}
    assert by_id[v1.id].is_latest is False


@pytest.mark.asyncio
async def test_three_replaces_form_a_chain_in_order(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()

    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1"), replace=True
    )
    v2 = await svc.upload_file(
        app_id,
        entity_id,
        record_id,
        "attachment",
        FakeUploadFile("doc_final.pdf", b"2"),
        replace=True,
    )
    v3 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"3"), replace=True
    )

    history = await svc.list_versions(v3.id)
    assert [f.version for f in history] == [3, 2, 1]
    assert [f.id for f in history] == [v3.id, v2.id, v1.id]

    # Looking up the chain from *any* version returns the same full history,
    # even though the filename changed and changed back along the way.
    history_from_v1 = await svc.list_versions(v1.id)
    assert [f.id for f in history_from_v1] == [v3.id, v2.id, v1.id]


@pytest.mark.asyncio
async def test_replace_scoped_to_record(svc: FileService) -> None:
    """replace=True must not let two different records' fields supersede
    each other just because the field_name matches."""
    app_id, entity_id = uuid.uuid4(), uuid.uuid4()
    record_a, record_b = uuid.uuid4(), uuid.uuid4()

    a = await svc.upload_file(
        app_id, entity_id, record_a, "attachment", FakeUploadFile("doc.pdf", b"a"), replace=True
    )
    b = await svc.upload_file(
        app_id, entity_id, record_b, "attachment", FakeUploadFile("doc.pdf", b"b"), replace=True
    )

    assert a.version == 1 and b.version == 1
    assert a.previous_version_id is None and b.previous_version_id is None


@pytest.mark.asyncio
async def test_replace_after_multiple_independent_uploads_does_not_error(svc: FileService) -> None:
    """If a field already has several independent (replace=False) files —
    e.g. a multi-file block — a later replace=True upload must not blow up
    picking "the" current latest; it should just supersede the newest one."""
    app_id, entity_id, record_id = _ids()

    a = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("a.pdf", b"a")
    )
    b = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("b.pdf", b"b")
    )

    c = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("c.pdf", b"c"), replace=True
    )

    assert c.version == max(a.version, b.version) + 1
    assert c.previous_version_id in (a.id, b.id)

    files = await svc.list_files(record_id)
    # The one replaced is gone from the default view; the untouched sibling remains.
    assert c.id in {f.id for f in files}
    assert len(files) == 2


@pytest.mark.asyncio
async def test_replace_scoped_to_field(svc: FileService) -> None:
    """replace=True on one field of a record must not supersede a file
    attached under a different field_name on the same record."""
    app_id, entity_id, record_id = _ids()

    a = await svc.upload_file(
        app_id, entity_id, record_id, "field_one", FakeUploadFile("doc.pdf", b"a"), replace=True
    )
    b = await svc.upload_file(
        app_id, entity_id, record_id, "field_two", FakeUploadFile("doc.pdf", b"b"), replace=True
    )

    assert a.version == 1 and b.version == 1
    assert a.previous_version_id is None and b.previous_version_id is None


# ------------------------------------------------------------------
# Listing
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_filters_by_field_name(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    await svc.upload_file(app_id, entity_id, record_id, "field_one", FakeUploadFile("a.pdf", b"a"))
    f2 = await svc.upload_file(
        app_id, entity_id, record_id, "field_two", FakeUploadFile("b.pdf", b"b")
    )

    files = await svc.list_files(record_id, field_name="field_two")
    assert [f.id for f in files] == [f2.id]


@pytest.mark.asyncio
async def test_list_files_all_versions_includes_superseded(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1"), replace=True
    )
    v2 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"2"), replace=True
    )

    default_view = await svc.list_files(record_id)
    all_view = await svc.list_files(record_id, include_all_versions=True)

    assert {f.id for f in default_view} == {v2.id}
    assert {f.id for f in all_view} == {v1.id, v2.id}


# ------------------------------------------------------------------
# Delete
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_latest_version_promotes_previous(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1"), replace=True
    )
    v2 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"2"), replace=True
    )

    await svc.delete_file(v2.id)

    files = await svc.list_files(record_id)
    assert [f.id for f in files] == [v1.id]
    assert files[0].is_latest is True


@pytest.mark.asyncio
async def test_delete_only_version_leaves_field_empty(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1")
    )

    await svc.delete_file(v1.id)

    files = await svc.list_files(record_id)
    assert files == []


@pytest.mark.asyncio
async def test_delete_historical_version_does_not_disturb_latest(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1"), replace=True
    )
    v2 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"2"), replace=True
    )

    await svc.delete_file(v1.id)

    files = await svc.list_files(record_id)
    assert [f.id for f in files] == [v2.id]
    assert files[0].is_latest is True


@pytest.mark.asyncio
async def test_delete_removes_object_from_storage(svc: FileService, storage: FakeStorage) -> None:
    app_id, entity_id, record_id = _ids()
    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1")
    )

    await svc.delete_file(v1.id)

    assert len(storage.deleted) == 1


@pytest.mark.asyncio
async def test_delete_unknown_file_raises_not_found(svc: FileService) -> None:
    with pytest.raises(RecordFileNotFoundError):
        await svc.delete_file(uuid.uuid4())


# ------------------------------------------------------------------
# Download
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_download_url_returns_presigned_url(svc: FileService) -> None:
    app_id, entity_id, record_id = _ids()
    v1 = await svc.upload_file(
        app_id, entity_id, record_id, "attachment", FakeUploadFile("doc.pdf", b"1")
    )

    read = await svc.get_download_url(v1.id, expires=120)

    assert read.download_url is not None
    assert "expires=120" in read.download_url


@pytest.mark.asyncio
async def test_get_download_url_unknown_file_raises_not_found(svc: FileService) -> None:
    with pytest.raises(RecordFileNotFoundError):
        await svc.get_download_url(uuid.uuid4())
