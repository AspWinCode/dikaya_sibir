"""ImportService: parse CSV/XLSX and bulk-create/upsert records."""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

MAX_IMPORT_ROWS = 100_000  # ТЗ Приложение A — not admin-configurable
MAX_IMPORT_FILE_SIZE = 50 * 1024 * 1024  # 50 MB — ТЗ Приложение A — not admin-configurable
_EXCEL_EXTS = {"xlsx", "xls"}
_CSV_EXTS = {"csv", "txt"}


@dataclass
class ImportResult:
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    aborted: bool = False


class ImportValidationError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class ImportService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def import_records(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        file_data: bytes,
        filename: str,
        column_map: dict[str, str] | None = None,
        actor_id: uuid.UUID | None = None,
        on_error: Literal["skip", "abort"] = "skip",
        key_field: str | None = None,
    ) -> ImportResult:
        """
        Parse the uploaded file, map columns to entity field names, validate and
        bulk-create (or upsert) records.

        column_map: {csv_header → entity_field_name}. Defaults to identity mapping.
        on_error: "skip" imports the valid rows and reports the rest as errors
            (default); "abort" rolls back every row from this import if even one
            fails (ТЗ 3.8 — "отменить весь импорт").
        key_field: entity field to match existing records against. When a row's
            value for this field matches an existing, non-deleted record, that
            record is updated instead of a new one being created (ТЗ 3.8 —
            "обновление существующих записей по ключевому полю").
        """
        if len(file_data) > MAX_IMPORT_FILE_SIZE:
            raise ImportValidationError(
                f"File exceeds the maximum import size of {MAX_IMPORT_FILE_SIZE // 1_048_576} MB",
            )

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in _CSV_EXTS:
            rows = self._parse_csv(file_data)
        elif ext in _EXCEL_EXTS:
            rows = self._parse_xlsx(file_data)
        else:
            raise ImportValidationError(
                f"Unsupported file type: {ext!r}. Upload a CSV or XLSX file."
            )

        if not rows:
            return ImportResult()

        if len(rows) > MAX_IMPORT_ROWS:
            raise ImportValidationError(
                f"File contains {len(rows)} rows, exceeding the limit of {MAX_IMPORT_ROWS}. "
                "Split it into smaller files.",
            )

        headers = list(rows[0].keys())
        effective_map: dict[str, str] = column_map or {h: h for h in headers}

        result = ImportResult(total=len(rows))

        from app.schemas.records import RecordCreate, RecordUpdate
        from app.services.records import RecordService, RecordValidationError
        from app.services.validation_rules import ValidationBlockedError

        svc = RecordService(self._db)

        # "abort" needs to undo every row this call created/updated the moment
        # one fails — a savepoint lets us do that without disturbing whatever
        # else is pending in the caller's transaction (e.g. the outbox audit
        # log entry the endpoint writes after this returns).
        savepoint = await self._db.begin_nested() if on_error == "abort" else None

        for row_num, row in enumerate(rows, start=2):
            payload: dict[str, Any] = {}
            for csv_col, field_name in effective_map.items():
                val = row.get(csv_col)
                if val is not None and val != "":
                    payload[field_name] = val

            if not payload:
                result.skipped += 1
                continue

            try:
                existing_id = (
                    await self._find_by_key(entity_id, key_field, payload) if key_field else None
                )
                if existing_id is not None:
                    await svc.update_record(
                        entity_id,
                        existing_id,
                        RecordUpdate(payload=payload),
                        app_id,
                        actor_id=actor_id,
                    )
                    result.updated += 1
                else:
                    await svc.create_record(
                        entity_id, RecordCreate(payload=payload), app_id, actor_id=actor_id
                    )
                    result.created += 1
            except (RecordValidationError, ValidationBlockedError) as exc:
                error_message = exc.message if isinstance(exc, ValidationBlockedError) else str(exc)
                result.errors.append({"row": row_num, "error": error_message, "data": payload})
                if on_error == "abort":
                    break
            except Exception as exc:
                result.errors.append(
                    {"row": row_num, "error": f"Unexpected error: {exc}", "data": payload}
                )
                if on_error == "abort":
                    break

        if savepoint is not None:
            if result.errors:
                await savepoint.rollback()
                result.created = 0
                result.updated = 0
                result.aborted = True
            else:
                await savepoint.commit()

        logger.info(
            "import_completed",
            app_id=str(app_id),
            entity_id=str(entity_id),
            total=result.total,
            created=result.created,
            updated=result.updated,
            skipped=result.skipped,
            error_count=len(result.errors),
            aborted=result.aborted,
        )
        return result

    async def _find_by_key(
        self,
        entity_id: uuid.UUID,
        key_field: str,
        payload: dict[str, Any],
    ) -> uuid.UUID | None:
        """Return the id of an existing, non-deleted record whose `key_field`
        matches this row's value for it — or None if there's no match or the
        row doesn't set that field."""
        from app.models.data import Record

        key_value = payload.get(key_field)
        if key_value is None:
            return None
        result = await self._db.execute(
            select(Record.id).where(
                Record.entity_id == entity_id,
                Record.is_deleted.is_(False),
                Record.payload[key_field].astext == str(key_value),
            )
        )
        return result.scalar_one_or_none()

    def preview_file(
        self,
        file_data: bytes,
        filename: str,
        sample_size: int = 5,
    ) -> dict[str, Any]:
        """
        Parse the file and return headers + first N rows without creating records.
        Returns: {headers, sample, total_rows}
        """
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in _CSV_EXTS:
            rows = self._parse_csv(file_data)
        elif ext in _EXCEL_EXTS:
            rows = self._parse_xlsx(file_data)
        else:
            raise ImportValidationError(
                f"Unsupported file type: {ext!r}. Upload a CSV or XLSX file."
            )

        if not rows:
            return {"headers": [], "sample": [], "total_rows": 0}

        headers = list(rows[0].keys())
        sample = [
            {k: (str(v) if v is not None else "") for k, v in row.items()}
            for row in rows[:sample_size]
        ]
        return {"headers": headers, "sample": sample, "total_rows": len(rows)}

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_csv(self, data: bytes) -> list[dict[str, str | None]]:
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    def _parse_xlsx(self, data: bytes) -> list[dict[str, Any]]:
        try:
            import openpyxl
        except ImportValidationError as exc:
            raise ImportValidationError(
                "openpyxl is required to parse Excel files. Contact your administrator.",
                status_code=501,
            ) from exc

        import io as _io  # already imported but shadow is fine

        wb = openpyxl.load_workbook(_io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        if ws is None:
            return []

        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if not all_rows:
            return []

        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(all_rows[0])]

        result: list[dict[str, Any]] = []
        for raw_row in all_rows[1:]:
            result.append(
                {headers[i]: (str(v) if v is not None else None) for i, v in enumerate(raw_row)}
            )
        return result
