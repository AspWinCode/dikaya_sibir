"""FileService: upload → scan → S3 → DB."""

import uuid

import structlog
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.antivirus import ClamAVClient
from app.core.config import settings
from app.core.metrics import file_uploads
from app.core.storage import S3Storage
from app.models.data import RecordFile
from app.schemas.records import RecordFileRead
from app.services.file_policy import FilePolicyService

logger = structlog.get_logger(__name__)


class FileError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class RecordFileNotFoundError(Exception):
    pass


class FileService:
    def __init__(self, db: AsyncSession, storage: S3Storage, av: ClamAVClient) -> None:
        self._db = db
        self._storage = storage
        self._av = av

    async def upload_file(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        record_id: uuid.UUID,
        field_name: str,
        upload: UploadFile,
        actor_id: uuid.UUID | None = None,
        replace: bool = False,
        max_files: int | None = None,
    ) -> RecordFileRead:
        """Upload a file for a record field.

        `replace` controls whether this upload versions the field's current
        file or adds an independent one — the same field_name is used both
        for single-value fields (replace=True: "Заменить" always supersedes
        the current file, regardless of filename) and multi-file attachment
        lists (replace=False, the default: every upload is independent, so
        several files can coexist under the same field_name).

        `max_files` lets a UI block tighten the platform's
        max_files_per_record ceiling (e.g. a block configured for at most 5
        attachments); it can only lower the ceiling, never raise it.
        """
        policy = await FilePolicyService(self._db).get()

        filename = upload.filename or "unnamed"
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if ext not in policy.allowed_extensions:
            file_uploads.labels(status="error").inc()
            raise FileError(f"File type '.{ext}' is not allowed")

        data = await upload.read()
        max_size_bytes = policy.max_file_size_mb * 1024 * 1024
        if len(data) > max_size_bytes:
            file_uploads.labels(status="error").inc()
            raise FileError(f"File exceeds maximum size of {policy.max_file_size_mb} MB")

        # ClamAV scan
        is_clean, verdict = await self._av.scan_bytes(data)
        if not is_clean:
            logger.warning("infected_file_blocked", filename=filename, verdict=verdict)
            file_uploads.labels(status="virus_detected").inc()
            raise FileError("File failed antivirus scan", status_code=422)

        previous: RecordFile | None = None
        if replace:
            # Lock the current latest row (if any) so two concurrent replace
            # uploads can't both end up marked latest. Not filtered by
            # filename — replacing "scan.pdf" with "scan_v2.pdf" still
            # versions the field's one file.
            prev_stmt = (
                select(RecordFile)
                .where(
                    RecordFile.record_id == record_id,
                    RecordFile.field_name == field_name,
                    RecordFile.is_latest.is_(True),
                )
                .order_by(RecordFile.version.desc())
                .limit(1)
                .with_for_update()
            )
            previous = (await self._db.execute(prev_stmt)).scalars().first()

        # Максимальное количество файлов на запись (ТЗ 3.7.1 / Приложение A).
        # A replace supersedes one file and adds one, so it never changes the
        # count — exclude the superseded row so a replace at the ceiling
        # doesn't get blocked by itself.
        effective_max = policy.max_files_per_record
        if max_files is not None:
            effective_max = min(max_files, effective_max)
        count_stmt = (
            select(func.count())
            .select_from(RecordFile)
            .where(
                RecordFile.record_id == record_id,
                RecordFile.is_latest.is_(True),
            )
        )
        if previous is not None:
            count_stmt = count_stmt.where(RecordFile.id != previous.id)
        current_count = (await self._db.execute(count_stmt)).scalar_one()
        if current_count + 1 > effective_max:
            file_uploads.labels(status="error").inc()
            raise FileError(f"Record already has the maximum of {effective_max} files")

        # Upload to S3
        s3_key = S3Storage.make_key(app_id, entity_id, record_id, filename)
        content_type = upload.content_type or "application/octet-stream"
        await self._storage.upload(
            settings.S3_BUCKET_FILES,
            s3_key,
            data,
            content_type=content_type,
            metadata={"uploaded-by": str(actor_id or "")},
        )

        if previous is not None:
            previous.is_latest = False

        # Persist to DB
        db_file = RecordFile(
            record_id=record_id,
            entity_id=entity_id,
            app_id=app_id,
            field_name=field_name,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            s3_key=s3_key,
            is_scanned=verdict != "SCAN_SKIPPED",
            is_infected=False,
            version=previous.version + 1 if previous else 1,
            is_latest=True,
            previous_version_id=previous.id if previous else None,
            created_by=actor_id,
        )
        self._db.add(db_file)
        await self._db.flush()
        file_uploads.labels(status="success").inc()
        logger.info(
            "file_uploaded",
            file_id=str(db_file.id),
            record_id=str(record_id),
            s3_key=s3_key,
            version=db_file.version,
        )
        return RecordFileRead.model_validate(db_file)

    async def get_download_url(self, file_id: uuid.UUID, expires: int = 3600) -> RecordFileRead:
        db_file = await self._fetch(file_id)
        url = await self._storage.get_presigned_url(
            settings.S3_BUCKET_FILES,
            db_file.s3_key,
            expires=expires,
            filename=db_file.original_filename,
        )
        read = RecordFileRead.model_validate(db_file)
        read.download_url = url
        return read

    async def list_files(
        self,
        record_id: uuid.UUID,
        field_name: str | None = None,
        include_all_versions: bool = False,
    ) -> list[RecordFileRead]:
        stmt = select(RecordFile).where(RecordFile.record_id == record_id)
        if field_name:
            stmt = stmt.where(RecordFile.field_name == field_name)
        if not include_all_versions:
            stmt = stmt.where(RecordFile.is_latest.is_(True))
        result = await self._db.execute(stmt)
        return [RecordFileRead.model_validate(f) for f in result.scalars()]

    async def list_versions(self, file_id: uuid.UUID) -> list[RecordFileRead]:
        """Full version history for the file identified by `file_id` (any
        version), newest first.

        Walks the previous_version_id chain rather than matching by filename:
        a "replace" upload can change the filename between versions (e.g.
        "scan.pdf" -> "scan_v2.pdf"), so the chain link is the only reliable
        way to group versions together.
        """
        anchor = await self._fetch(file_id)
        chain: dict[uuid.UUID, RecordFile] = {anchor.id: anchor}

        cur = anchor
        while cur.previous_version_id is not None:
            cur = await self._fetch(cur.previous_version_id)
            chain[cur.id] = cur

        cur = anchor
        while True:
            result = await self._db.execute(
                select(RecordFile).where(RecordFile.previous_version_id == cur.id)
            )
            successor = result.scalar_one_or_none()
            if successor is None:
                break
            chain[successor.id] = successor
            cur = successor

        ordered = sorted(chain.values(), key=lambda f: f.version, reverse=True)
        return [RecordFileRead.model_validate(f) for f in ordered]

    async def delete_file(self, file_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> None:
        db_file = await self._fetch(file_id)

        # Deleting the current version falls back to the previous one (if any)
        # rather than silently losing the whole version chain from view.
        if db_file.is_latest and db_file.previous_version_id is not None:
            previous = await self._fetch(db_file.previous_version_id)
            previous.is_latest = True

        # Remove from S3
        try:
            await self._storage.delete(settings.S3_BUCKET_FILES, db_file.s3_key)
        except Exception as exc:
            logger.warning("s3_delete_failed", key=db_file.s3_key, error=str(exc))

        await self._db.delete(db_file)
        await self._db.flush()
        logger.info("file_deleted", file_id=str(file_id))

    async def _fetch(self, file_id: uuid.UUID) -> RecordFile:
        result = await self._db.execute(select(RecordFile).where(RecordFile.id == file_id))
        f = result.scalar_one_or_none()
        if f is None:
            raise RecordFileNotFoundError(str(file_id))
        return f
