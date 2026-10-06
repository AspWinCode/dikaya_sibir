import uuid

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from app.api.deps import AuthDep, DbDep
from app.schemas.documents import (
    DOC_TYPES,
    DocTypeConfigRead,
    DocTypeConfigUpdate,
    DocumentRegistrationRead,
    FilingCaseCreate,
    FilingCaseRead,
    FilingCaseUpdate,
    RegisterDocumentRequest,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.exports import ExportError, ExportService
from app.services.registrar import (
    FilingCaseNotFoundError,
    RegistrarService,
    RegistrationConflictError,
)

router = APIRouter(prefix="/apps/{app_id}/documents", tags=["documents"])

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


# ------------------------------------------------------------------
# Doc type numbering configuration (ТЗ 3.10.1)
# ------------------------------------------------------------------

@router.get("/doc-types", response_model=list[DocTypeConfigRead])
async def list_doc_type_configs(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> list[DocTypeConfigRead]:
    await _check_app(app_id, current_user, db)
    configs = await RegistrarService(db).list_doc_type_configs(app_id)
    return [DocTypeConfigRead.model_validate(c) for c in configs]


@router.put("/doc-types/{doc_type}", response_model=DocTypeConfigRead)
async def update_doc_type_config(
    app_id: uuid.UUID, doc_type: str, body: DocTypeConfigUpdate, current_user: AuthDep, db: DbDep,
) -> DocTypeConfigRead:
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown doc_type {doc_type!r}")
    if not current_user.has_role("platform_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a platform admin can change numbering rules")
    await _check_app(app_id, current_user, db)
    config = await RegistrarService(db).update_doc_type_config(app_id, doc_type, body)
    return DocTypeConfigRead.model_validate(config)


# ------------------------------------------------------------------
# Registration (ТЗ 3.10.1)
# ------------------------------------------------------------------

@router.post("/register", response_model=DocumentRegistrationRead, status_code=status.HTTP_201_CREATED)
async def register_document(
    app_id: uuid.UUID, body: RegisterDocumentRequest, current_user: AuthDep, db: DbDep,
) -> DocumentRegistrationRead:
    await _check_app(app_id, current_user, db)
    try:
        reg = await RegistrarService(db).register_document(
            app_id, body.entity_id, body.record_id, body.doc_type,
            department_code=body.department_code, filing_case_id=body.filing_case_id,
            actor_id=current_user.user_id,
        )
    except RegistrationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Number {exc} already registered") from exc
    return DocumentRegistrationRead.model_validate(reg)


@router.get("/registrations", response_model=list[DocumentRegistrationRead])
async def list_registrations(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    doc_type: str | None = Query(default=None),
    filing_case_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[DocumentRegistrationRead]:
    await _check_app(app_id, current_user, db)
    regs = await RegistrarService(db).list_registrations(app_id, doc_type=doc_type, filing_case_id=filing_case_id, limit=limit)
    return [DocumentRegistrationRead.model_validate(r) for r in regs]


# ------------------------------------------------------------------
# Filing cases — номенклатура дел (ТЗ 3.10.2)
# ------------------------------------------------------------------

@router.get("/filing-cases", response_model=list[FilingCaseRead])
async def list_filing_cases(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> list[FilingCaseRead]:
    await _check_app(app_id, current_user, db)
    cases = await RegistrarService(db).list_filing_cases(app_id)
    return [FilingCaseRead.model_validate(c) for c in cases]


@router.post("/filing-cases", response_model=FilingCaseRead, status_code=status.HTTP_201_CREATED)
async def create_filing_case(
    app_id: uuid.UUID, body: FilingCaseCreate, current_user: AuthDep, db: DbDep,
) -> FilingCaseRead:
    await _check_app(app_id, current_user, db)
    try:
        case = await RegistrarService(db).create_filing_case(app_id, body)
    except FilingCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Parent case {exc} not found") from exc
    return FilingCaseRead.model_validate(case)


@router.patch("/filing-cases/{case_id}", response_model=FilingCaseRead)
async def update_filing_case(
    app_id: uuid.UUID, case_id: uuid.UUID, body: FilingCaseUpdate, current_user: AuthDep, db: DbDep,
) -> FilingCaseRead:
    await _check_app(app_id, current_user, db)
    try:
        case = await RegistrarService(db).update_filing_case(app_id, case_id, body)
    except FilingCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing case not found") from exc
    return FilingCaseRead.model_validate(case)


@router.delete("/filing-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_filing_case(app_id: uuid.UUID, case_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await RegistrarService(db).delete_filing_case(app_id, case_id)
    except FilingCaseNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Filing case not found") from exc


@router.get("/filing-cases/export")
async def export_filing_cases(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    format: str = Query(default="csv", pattern=r"^(csv|xlsx|pdf)$"),
) -> Response:
    await _check_app(app_id, current_user, db)
    cases = await RegistrarService(db).list_filing_cases(app_id)
    headers = ["index_code", "title", "status", "retention_years", "storage_location", "close_by", "closed_at"]
    rows = [
        {
            "index_code": c.index_code, "title": c.title, "status": c.status,
            "retention_years": c.retention_years, "storage_location": c.storage_location,
            "close_by": c.close_by.isoformat() if c.close_by else None,
            "closed_at": c.closed_at.isoformat() if c.closed_at else None,
        }
        for c in cases
    ]
    try:
        if format == "csv":
            payload = ExportService._to_csv(headers, rows)
        elif format == "xlsx":
            payload = ExportService._to_xlsx(headers, rows)
        else:
            payload = ExportService._to_pdf(headers, rows)
    except ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return Response(
        content=payload,
        media_type=CONTENT_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="filing_cases.{format}"'},
    )
