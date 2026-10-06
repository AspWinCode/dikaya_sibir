import json
import uuid
from typing import Any, Literal

import structlog
from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response

from app.api.deps import AuthDep, DbDep
from app.core import field_crypto
from app.core.antivirus import get_antivirus
from app.core.rate_limit import limiter
from app.core.storage import get_storage
from app.schemas.common import CursorPage
from app.schemas.records import (
    RecordCreate,
    RecordFileRead,
    RecordListParams,
    RecordRead,
    RecordUpdate,
    parse_filters,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.audit import AuditService
from app.services.entities import EntityNotFoundError, EntityService
from app.services.exports import ExportError, ExportService
from app.services.files import FileError, FileNotFoundError, FileService
from app.services.imports import ImportError as ImportFileError
from app.services.imports import ImportService
from app.services.records import RecordNotFoundError, RecordService, RecordValidationError
from app.services.rules import RuleService
from app.services.security import ABACService, FieldRestrictions
from app.services.validation_rules import ValidationBlockedError

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/apps/{app_id}/entities/{entity_id}/records",
    tags=["records"],
)


async def _resolve_entity(app_id: uuid.UUID, entity_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    """Verify app is accessible and entity belongs to it."""
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc

    try:
        await EntityService(db).get_entity(app_id, entity_id)
    except EntityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entity not found") from exc


def _apply_abac(
    record: RecordRead, denied_read: set[str], mask_fields: set[str] = frozenset()
) -> RecordRead:
    """Return a copy of the record with denied fields stripped and
    sensitive-but-unauthorized fields masked (ТЗ 3.13)."""
    if not denied_read and not mask_fields:
        return record
    result: dict[str, Any] = {}
    for k, v in record.payload.items():
        if k in denied_read:
            continue
        result[k] = field_crypto.mask_value(v) if k in mask_fields else v
    return record.model_copy(update={"payload": result})


async def _sensitive_mask_fields(
    db: DbDep, entity_id: uuid.UUID, current_user: AuthDep, restrictions: FieldRestrictions
) -> set[str]:
    """Fields marked Field.is_sensitive that this caller hasn't been
    explicitly granted read access to (platform_admin always sees
    everything). Everything else about a sensitive field's storage is
    handled inside RecordService — this only decides display masking."""
    if current_user.has_role("platform_admin"):
        return set()
    sensitive = await RecordService(db).get_sensitive_field_names(entity_id)
    if not sensitive:
        return set()
    return sensitive - restrictions.explicit_read_allow - restrictions.denied_read


# ------------------------------------------------------------------
# Records
# ------------------------------------------------------------------

@router.get("", response_model=CursorPage[RecordRead])
async def list_records(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    filter: list[str] = Query(default=[]),  # ?filter=name:eq:John&filter=age:gte:18
    sort: str | None = Query(default=None),
    sort_dir: str = Query(default="asc", pattern=r"^(asc|desc)$"),
    include_deleted: bool = Query(default=False),
) -> CursorPage[RecordRead]:
    await _resolve_entity(app_id, entity_id, current_user, db)

    try:
        parsed_filters = parse_filters(filter)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    params = RecordListParams(
        cursor=cursor,
        limit=limit,
        filters=parsed_filters,
        sort_field=sort,
        sort_dir=sort_dir,
        include_deleted=include_deleted and current_user.has_role("platform_admin", "app_admin"),
    )
    try:
        page = await RecordService(db).list_records(
            entity_id, params, actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
    except RecordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    restrictions = await ABACService(db).get_restrictions(entity_id, current_user.roles)
    mask_fields = await _sensitive_mask_fields(db, entity_id, current_user, restrictions)
    if restrictions.denied_read or mask_fields:
        page = page.model_copy(update={
            "items": [_apply_abac(r, restrictions.denied_read, mask_fields) for r in page.items]
        })
    return page


@router.post("", response_model=RecordRead, status_code=status.HTTP_201_CREATED)
async def create_record(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    body: RecordCreate,
    current_user: AuthDep,
    db: DbDep,
) -> RecordRead:
    await _resolve_entity(app_id, entity_id, current_user, db)

    restrictions = await ABACService(db).get_restrictions(entity_id, current_user.roles)
    denied = restrictions.check_write(list(body.payload.keys()))
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Write access denied for fields: {denied}",
        )

    try:
        record = await RecordService(db).create_record(
            entity_id, body, app_id, actor_id=current_user.user_id
        )
    except RecordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValidationBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message) from exc

    try:
        await RuleService(db).evaluate_rules_for_event(
            app_id, entity_id, record.id, record.payload, "record.created",
            actor_id=current_user.user_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("rule_evaluation_failed", entity_id=str(entity_id))

    # The audit log itself is not encrypted — mask sensitive fields here too,
    # or marking a field "sensitive" would be undone by its own audit trail.
    sensitive_names = await RecordService(db).get_sensitive_field_names(entity_id)
    audit_payload = (
        {k: (field_crypto.mask_value(v) if k in sensitive_names else v) for k, v in record.payload.items()}
        if sensitive_names else record.payload
    )
    await AuditService(db).log(
        "record.created",
        user_id=current_user.user_id,
        resource_type="record",
        resource_id=str(record.id),
        details={"app_id": str(app_id), "entity_id": str(entity_id), "payload": audit_payload},
    )
    mask_fields = await _sensitive_mask_fields(db, entity_id, current_user, restrictions)
    return _apply_abac(record, restrictions.denied_read, mask_fields)


_EXPORT_CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv; charset=utf-8",
    "pdf": "application/pdf",
}


@router.get("/export", tags=["records"])
async def export_records(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    format: str = Query(default="xlsx", pattern=r"^(xlsx|csv|pdf)$"),
    filter: list[str] = Query(default=[]),
    sort: str | None = Query(default=None),
    sort_dir: str = Query(default="asc", pattern=r"^(asc|desc)$"),
    limit: int = Query(default=5000, ge=1, le=10000, description="Max rows to export"),
) -> Response:
    """Export entity records as XLSX, CSV, or PDF. Returns the file directly."""
    await _resolve_entity(app_id, entity_id, current_user, db)

    try:
        parsed_filters = parse_filters(filter)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    params = RecordListParams(
        limit=limit,
        filters=parsed_filters,
        sort_field=sort,
        sort_dir=sort_dir,
    )

    try:
        file_bytes = await ExportService(db).export(
            entity_id, params, format=format,
            actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
    except ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    content_type = _EXPORT_CONTENT_TYPES[format]
    filename = f"export_{entity_id}.{format}"
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# NOTE: registered before GET "/{record_id}" — a bare /export path would
# otherwise match the {record_id}: uuid.UUID route first (and fail 422,
# since "export" isn't a valid UUID) since Starlette matches routes in
# registration order. Same reasoning applies to any other literal-suffix
# route under this prefix (e.g. /import) if one is ever added as a GET.
@router.get("/{record_id}", response_model=RecordRead)
async def get_record(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> RecordRead:
    await _resolve_entity(app_id, entity_id, current_user, db)
    try:
        record = await RecordService(db).get_record(
            entity_id, record_id, actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found") from exc

    restrictions = await ABACService(db).get_restrictions(entity_id, current_user.roles)
    mask_fields = await _sensitive_mask_fields(db, entity_id, current_user, restrictions)
    return _apply_abac(record, restrictions.denied_read, mask_fields)


@router.patch("/{record_id}", response_model=RecordRead)
async def update_record(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    body: RecordUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> RecordRead:
    await _resolve_entity(app_id, entity_id, current_user, db)

    restrictions = await ABACService(db).get_restrictions(entity_id, current_user.roles)
    denied = restrictions.check_write(list(body.payload.keys()))
    if denied:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Write access denied for fields: {denied}",
        )

    changed_fields = list(body.payload.keys())

    try:
        # Pre-update snapshot, just for the audit diff below — RecordService.update_record
        # re-checks ABAC/existence itself right after, so this doesn't weaken enforcement.
        previous = await RecordService(db).get_record(
            entity_id, record_id, actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
        record = await RecordService(db).update_record(
            entity_id, record_id, body, app_id,
            actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found") from exc
    except RecordValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValidationBlockedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message) from exc

    try:
        await RuleService(db).evaluate_rules_for_event(
            app_id, entity_id, record.id, record.payload, "record.updated",
            changed_fields=changed_fields, actor_id=current_user.user_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("rule_evaluation_failed", entity_id=str(entity_id))

    sensitive_names = await RecordService(db).get_sensitive_field_names(entity_id)

    def _audit_value(f: str, v: Any) -> Any:
        return field_crypto.mask_value(v) if f in sensitive_names else v

    field_changes = {
        f: {"old": _audit_value(f, previous.payload.get(f)), "new": _audit_value(f, record.payload.get(f))}
        for f in changed_fields
    }
    await AuditService(db).log(
        "record.updated",
        user_id=current_user.user_id,
        resource_type="record",
        resource_id=str(record_id),
        details={
            "app_id": str(app_id), "entity_id": str(entity_id),
            "changed_fields": changed_fields, "field_changes": field_changes,
        },
    )
    mask_fields = sensitive_names - restrictions.explicit_read_allow - restrictions.denied_read \
        if not current_user.has_role("platform_admin") else set()
    return _apply_abac(record, restrictions.denied_read, mask_fields)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    hard: bool = Query(default=False),
) -> None:
    await _resolve_entity(app_id, entity_id, current_user, db)
    if hard and not current_user.has_role("platform_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Hard delete requires platform_admin")
    try:
        # Pre-delete snapshot, just for the audit trail — delete_record re-checks
        # ABAC/existence itself right after, so this doesn't weaken enforcement.
        deleted = await RecordService(db).get_record(
            entity_id, record_id, actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
        await RecordService(db).delete_record(
            entity_id, record_id, hard=hard,
            actor_id=current_user.user_id, actor_roles=current_user.roles,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found") from exc

    sensitive_names = await RecordService(db).get_sensitive_field_names(entity_id)
    audit_payload = (
        {k: (field_crypto.mask_value(v) if k in sensitive_names else v) for k, v in deleted.payload.items()}
        if sensitive_names else deleted.payload
    )
    await AuditService(db).log(
        "record.deleted",
        user_id=current_user.user_id,
        resource_type="record",
        resource_id=str(record_id),
        details={
            "app_id": str(app_id), "entity_id": str(entity_id), "hard": hard,
            "payload": audit_payload,
        },
    )


@router.post("/{record_id}/restore", response_model=RecordRead)
async def restore_record(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> RecordRead:
    await _resolve_entity(app_id, entity_id, current_user, db)
    try:
        return await RecordService(db).restore_record(entity_id, record_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deleted record not found") from exc


# ------------------------------------------------------------------
# File attachments (nested under records)
# ------------------------------------------------------------------

@router.post("/{record_id}/files", response_model=RecordFileRead, status_code=status.HTTP_201_CREATED, tags=["files"])
@limiter.limit("20/minute")
async def upload_file(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    field_name: str,
    file: UploadFile,
    request: Request,
    current_user: AuthDep,
    db: DbDep,
    replace: bool = Query(
        default=False,
        description="Version the field's current file instead of adding an independent one",
    ),
    max_files: int | None = Query(
        default=None, ge=1,
        description="Block-level cap on files per record; can only tighten the platform ceiling, never raise it",
    ),
) -> RecordFileRead:
    await _resolve_entity(app_id, entity_id, current_user, db)
    svc = FileService(db, get_storage(), get_antivirus())
    try:
        return await svc.upload_file(
            app_id, entity_id, record_id, field_name, file,
            actor_id=current_user.user_id, replace=replace, max_files=max_files,
        )
    except FileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/{record_id}/files", response_model=list[RecordFileRead], tags=["files"])
async def list_files(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    field_name: str | None = Query(default=None),
    all_versions: bool = Query(default=False, description="Include superseded file versions"),
) -> list[RecordFileRead]:
    await _resolve_entity(app_id, entity_id, current_user, db)
    svc = FileService(db, get_storage(), get_antivirus())
    return await svc.list_files(record_id, field_name=field_name, include_all_versions=all_versions)


@router.get("/{record_id}/files/{file_id}/versions", response_model=list[RecordFileRead], tags=["files"])
async def list_file_versions(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> list[RecordFileRead]:
    """Version history (newest first) for the file identified by `file_id` (any version)."""
    await _resolve_entity(app_id, entity_id, current_user, db)
    svc = FileService(db, get_storage(), get_antivirus())
    try:
        return await svc.list_versions(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc


@router.get("/{record_id}/files/{file_id}/download", response_model=RecordFileRead, tags=["files"])
async def get_download_url(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    expires: int = Query(default=3600, ge=60, le=86400),
) -> RecordFileRead:
    await _resolve_entity(app_id, entity_id, current_user, db)
    svc = FileService(db, get_storage(), get_antivirus())
    try:
        return await svc.get_download_url(file_id, expires=expires)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc


@router.post("/import/preview", tags=["records"])
@limiter.limit("20/minute")
async def preview_import(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    current_user: AuthDep,
    db: DbDep,
) -> dict:
    """Return CSV/XLSX headers and first 5 rows without creating records."""
    await _resolve_entity(app_id, entity_id, current_user, db)
    data = await file.read()
    filename = file.filename or "import.csv"
    try:
        result = ImportService(db).preview_file(data, filename)
    except ImportFileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return result


@router.post("/import", tags=["records"])
@limiter.limit("10/minute")
async def import_records(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    file: UploadFile,
    request: Request,
    current_user: AuthDep,
    db: DbDep,
    column_map: str | None = Query(default=None, description="JSON map of CSV header → field name"),
    on_error: Literal["skip", "abort"] = Query(
        default="skip",
        description="'skip': import valid rows, report the rest as errors. 'abort': roll back the whole import if any row fails.",
    ),
    key_field: str | None = Query(
        default=None, description="Field to match existing records by — matches are updated instead of duplicated",
    ),
) -> dict[str, Any]:
    """
    Bulk-import records from a CSV or XLSX file.
    Returns a report: {total, created, updated, skipped, aborted, errors:[{row, error, data}]}.
    """
    await _resolve_entity(app_id, entity_id, current_user, db)

    parsed_map: dict[str, str] | None = None
    if column_map:
        try:
            parsed_map = json.loads(column_map)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="column_map must be valid JSON",
            ) from exc

    data = await file.read()
    filename = file.filename or "import.csv"

    try:
        result = await ImportService(db).import_records(
            app_id, entity_id, data, filename,
            column_map=parsed_map, actor_id=current_user.user_id,
            on_error=on_error, key_field=key_field,
        )
    except ImportFileError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return {
        "total": result.total,
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "aborted": result.aborted,
        "errors": result.errors,
    }


@router.delete("/{record_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["files"])
async def delete_file(
    app_id: uuid.UUID,
    entity_id: uuid.UUID,
    record_id: uuid.UUID,
    file_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    await _resolve_entity(app_id, entity_id, current_user, db)
    svc = FileService(db, get_storage(), get_antivirus())
    try:
        await svc.delete_file(file_id, actor_id=current_user.user_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc
