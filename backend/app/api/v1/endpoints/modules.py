import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.modules import AppModuleRead, ModuleInstallResult, ModuleRead
from app.services.modules import (
    AppModuleNotFoundError,
    ModuleDependencyError,
    ModulePermissionError,
    ModuleService,
)

router = APIRouter(tags=["modules"])


def _service(db: DbDep) -> ModuleService:
    return ModuleService(db)


@router.get("/modules", response_model=list[ModuleRead])
async def list_modules(
    current_user: AuthDep,
    db: DbDep,
    app_id: uuid.UUID | None = Query(default=None),
) -> list[ModuleRead]:
    return await _service(db).list_modules(app_id=app_id)


@router.get("/apps/{app_id}/modules", response_model=list[AppModuleRead])
async def list_app_modules(
    app_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[AppModuleRead]:
    return await _service(db).list_app_modules(app_id)


@router.post("/apps/{app_id}/modules/{module_code}/install", response_model=ModuleInstallResult)
async def install_module(
    app_id: uuid.UUID,
    module_code: str,
    current_user: AuthDep,
    db: DbDep,
) -> ModuleInstallResult:
    try:
        return await _service(db).install_module(
            app_id,
            module_code,
            actor_id=current_user.user_id,
        )
    except AppModuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ModulePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.delete("/apps/{app_id}/modules/{module_code}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_module(
    app_id: uuid.UUID,
    module_code: str,
    current_user: AuthDep,
    db: DbDep,
) -> None:
    try:
        await _service(db).uninstall_module(
            app_id,
            module_code,
            actor_id=current_user.user_id,
        )
    except ModuleDependencyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except AppModuleNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ModulePermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
