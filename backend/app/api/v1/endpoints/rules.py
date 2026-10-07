import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.rules import (
    CycleCheckResponse,
    ProcessStepCreate,
    ProcessStepRead,
    ProcessStepsReorder,
    ProcessStepUpdate,
    RuleConflictLogRead,
    RuleCreate,
    RuleExecutionLogRead,
    RuleRead,
    RuleTestRequest,
    RuleTestResponse,
    RuleUpdate,
    RuleWebhookDeliveryRead,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.rules import (
    RuleCycleError,
    RuleNotFoundError,
    RuleService,
    StepNotFoundError,
    StepValidationError,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/apps/{app_id}/rules", tags=["rules"])


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


def _rule_not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")


@router.get("", response_model=list[RuleRead])
async def list_rules(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    entity_id: uuid.UUID | None = Query(default=None),
    active_only: bool = Query(default=False),
) -> list[RuleRead]:
    await _check_app(app_id, current_user, db)
    return await RuleService(db).list_rules(app_id, entity_id=entity_id, active_only=active_only)


@router.post("", response_model=RuleRead, status_code=status.HTTP_201_CREATED)
async def create_rule(
    app_id: uuid.UUID, body: RuleCreate, current_user: AuthDep, db: DbDep
) -> RuleRead:
    await _check_app(app_id, current_user, db)
    return await RuleService(db).create_rule(app_id, body, creator_id=current_user.user_id)


@router.get("/cycles", response_model=CycleCheckResponse)
async def check_cycles(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> CycleCheckResponse:
    await _check_app(app_id, current_user, db)
    return await RuleService(db).check_cycles(app_id)


@router.get(
    "/conflicts",
    response_model=list[RuleConflictLogRead],
    summary="Rule priority conflict log (ТЗ 3.5.4)",
)
async def get_rule_conflicts(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    entity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RuleConflictLogRead]:
    await _check_app(app_id, current_user, db)
    return await RuleService(db).list_conflicts(app_id, entity_id=entity_id, limit=limit)


@router.get(
    "/webhook-deliveries",
    response_model=list[RuleWebhookDeliveryRead],
    summary="call_webhook action delivery log",
)
async def get_rule_webhook_deliveries(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    entity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RuleWebhookDeliveryRead]:
    await _check_app(app_id, current_user, db)
    return await RuleService(db).list_webhook_deliveries(app_id, entity_id=entity_id, limit=limit)


@router.get("/{rule_id}", response_model=RuleRead)
async def get_rule(
    app_id: uuid.UUID, rule_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> RuleRead:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).get_rule(app_id, rule_id)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc


@router.patch("/{rule_id}", response_model=RuleRead)
async def update_rule(
    app_id: uuid.UUID, rule_id: uuid.UUID, body: RuleUpdate, current_user: AuthDep, db: DbDep
) -> RuleRead:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).update_rule(app_id, rule_id, body)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc
    except RuleCycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Activating this rule creates a dependency cycle",
                "cycles": exc.cycles,
            },
        ) from exc


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    app_id: uuid.UUID, rule_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await RuleService(db).delete_rule(app_id, rule_id)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc


@router.post("/{rule_id}/activate", response_model=RuleRead)
async def activate_rule(
    app_id: uuid.UUID, rule_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> RuleRead:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).activate_rule(app_id, rule_id)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc
    except RuleCycleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "This rule creates a dependency cycle", "cycles": exc.cycles},
        ) from exc


@router.post("/{rule_id}/deactivate", response_model=RuleRead)
async def deactivate_rule(
    app_id: uuid.UUID, rule_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> RuleRead:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).deactivate_rule(app_id, rule_id)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc


@router.post("/{rule_id}/test", response_model=RuleTestResponse)
async def test_rule(
    app_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: RuleTestRequest,
    current_user: AuthDep,
    db: DbDep,
) -> RuleTestResponse:
    """Dry-run: evaluate rule against a sample payload without writing to DB."""
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).test_rule(app_id, rule_id, body)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc


@router.get("/{rule_id}/logs", response_model=list[RuleExecutionLogRead])
async def get_rule_logs(
    app_id: uuid.UUID,
    rule_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[RuleExecutionLogRead]:
    await _check_app(app_id, current_user, db)
    return await RuleService(db).list_logs(app_id, rule_id=rule_id, limit=limit)


# ------------------------------------------------------------------
# Process steps — ordered CRUD bound to a rule (stored in rule.actions)
# ------------------------------------------------------------------


def _bad_step(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _step_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")


@router.get("/{rule_id}/steps", response_model=list[ProcessStepRead])
async def list_steps(
    app_id: uuid.UUID, rule_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[ProcessStepRead]:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).list_steps(app_id, rule_id)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc


@router.post(
    "/{rule_id}/steps", response_model=ProcessStepRead, status_code=status.HTTP_201_CREATED
)
async def add_step(
    app_id: uuid.UUID, rule_id: uuid.UUID, body: ProcessStepCreate, current_user: AuthDep, db: DbDep
) -> ProcessStepRead:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).add_step(app_id, rule_id, body)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc
    except StepValidationError as exc:
        raise _bad_step(exc) from exc


@router.put("/{rule_id}/steps/reorder", response_model=list[ProcessStepRead])
async def reorder_steps(
    app_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: ProcessStepsReorder,
    current_user: AuthDep,
    db: DbDep,
) -> list[ProcessStepRead]:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).reorder_steps(app_id, rule_id, body.step_ids)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc
    except StepValidationError as exc:
        raise _bad_step(exc) from exc


@router.patch("/{rule_id}/steps/{step_id}", response_model=ProcessStepRead)
async def update_step(
    app_id: uuid.UUID,
    rule_id: uuid.UUID,
    step_id: str,
    body: ProcessStepUpdate,
    current_user: AuthDep,
    db: DbDep,
) -> ProcessStepRead:
    await _check_app(app_id, current_user, db)
    try:
        return await RuleService(db).update_step(app_id, rule_id, step_id, body)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc
    except StepNotFoundError as exc:
        raise _step_not_found() from exc
    except StepValidationError as exc:
        raise _bad_step(exc) from exc


@router.delete("/{rule_id}/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(
    app_id: uuid.UUID, rule_id: uuid.UUID, step_id: str, current_user: AuthDep, db: DbDep
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await RuleService(db).delete_step(app_id, rule_id, step_id)
    except RuleNotFoundError as exc:
        raise _rule_not_found(exc) from exc
    except StepNotFoundError as exc:
        raise _step_not_found() from exc
