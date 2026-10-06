import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.workflow import (
    ApprovalChainDefCreate,
    ApprovalChainDefRead,
    ApprovalChainDefUpdate,
    ApprovalChainInstanceRead,
    ApprovalDecisionRequest,
    AssignInstanceRequest,
    AvailableTransitionRead,
    StartInstanceRequest,
    StateDefCreate,
    StateDefRead,
    StateDefUpdate,
    TransitionDefCreate,
    TransitionDefRead,
    TransitionDefUpdate,
    TransitionLogRead,
    TransitionRequest,
    TransitionResponse,
    WorkflowDefCreate,
    WorkflowDefRead,
    WorkflowDefUpdate,
    WorkflowInstanceRead,
)
from app.services.apps import AppNotFoundError, AppService
from app.services.workflow import (
    WorkflowConcurrentModificationError,
    WorkflowInstanceAlreadyExistsError,
    WorkflowInstanceNotFoundError,
    WorkflowNotFoundError,
    WorkflowService,
    WorkflowStateNotFoundError,
    WorkflowTransitionError,
    WorkflowTransitionNotFoundError,
)

from pydantic import BaseModel


class CancelInstanceRequest(BaseModel):
    reason: str | None = None

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/apps/{app_id}/workflows", tags=["workflows"])


async def _check_app(app_id: uuid.UUID, current_user: AuthDep, db: DbDep) -> None:
    try:
        await AppService(db).get_app(app_id, actor_id=current_user.user_id)
    except AppNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found") from exc


def _wf_not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")


def _instance_not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow instance not found")


# ==================================================================
# WorkflowDef
# ==================================================================

@router.get("", response_model=list[WorkflowDefRead])
async def list_workflows(
    app_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    entity_id: uuid.UUID | None = Query(default=None),
    active_only: bool = Query(default=False),
) -> list[WorkflowDefRead]:
    await _check_app(app_id, current_user, db)
    return await WorkflowService(db).list_workflows(app_id, entity_id=entity_id, active_only=active_only)


@router.post("", response_model=WorkflowDefRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    app_id: uuid.UUID, body: WorkflowDefCreate, current_user: AuthDep, db: DbDep
) -> WorkflowDefRead:
    await _check_app(app_id, current_user, db)
    return await WorkflowService(db).create_workflow(app_id, body)


@router.get("/{workflow_id}", response_model=WorkflowDefRead)
async def get_workflow(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> WorkflowDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc


@router.patch("/{workflow_id}", response_model=WorkflowDefRead)
async def update_workflow(
    app_id: uuid.UUID, workflow_id: uuid.UUID, body: WorkflowDefUpdate,
    current_user: AuthDep, db: DbDep,
) -> WorkflowDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).update_workflow(app_id, workflow_id, body)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).delete_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc


@router.post("/{workflow_id}/activate", response_model=WorkflowDefRead)
async def activate_workflow(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> WorkflowDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).activate_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc


@router.post("/{workflow_id}/deactivate", response_model=WorkflowDefRead)
async def deactivate_workflow(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> WorkflowDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).deactivate_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc


# ==================================================================
# StateDef
# ==================================================================

@router.get("/{workflow_id}/states", response_model=list[StateDefRead])
async def list_states(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[StateDefRead]:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).list_states(workflow_id)


@router.post("/{workflow_id}/states", response_model=StateDefRead, status_code=status.HTTP_201_CREATED)
async def create_state(
    app_id: uuid.UUID, workflow_id: uuid.UUID, body: StateDefCreate,
    current_user: AuthDep, db: DbDep,
) -> StateDefRead:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).create_state(workflow_id, body)


@router.patch("/{workflow_id}/states/{state_id}", response_model=StateDefRead)
async def update_state(
    app_id: uuid.UUID, workflow_id: uuid.UUID, state_id: uuid.UUID,
    body: StateDefUpdate, current_user: AuthDep, db: DbDep,
) -> StateDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).update_state(workflow_id, state_id, body)
    except (WorkflowNotFoundError, WorkflowStateNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc


@router.delete("/{workflow_id}/states/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_state(
    app_id: uuid.UUID, workflow_id: uuid.UUID, state_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).delete_state(workflow_id, state_id)
    except WorkflowStateNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State not found") from exc


# ==================================================================
# TransitionDef
# ==================================================================

@router.get("/{workflow_id}/transitions", response_model=list[TransitionDefRead])
async def list_transitions(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[TransitionDefRead]:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).list_transitions(workflow_id)


@router.post("/{workflow_id}/transitions", response_model=TransitionDefRead,
             status_code=status.HTTP_201_CREATED)
async def create_transition(
    app_id: uuid.UUID, workflow_id: uuid.UUID, body: TransitionDefCreate,
    current_user: AuthDep, db: DbDep,
) -> TransitionDefRead:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).create_transition(workflow_id, body)


@router.patch("/{workflow_id}/transitions/{transition_id}", response_model=TransitionDefRead)
async def update_transition(
    app_id: uuid.UUID, workflow_id: uuid.UUID, transition_id: uuid.UUID,
    body: TransitionDefUpdate, current_user: AuthDep, db: DbDep,
) -> TransitionDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).update_transition(workflow_id, transition_id, body)
    except WorkflowTransitionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition not found") from exc


@router.delete("/{workflow_id}/transitions/{transition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transition(
    app_id: uuid.UUID, workflow_id: uuid.UUID, transition_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).delete_transition(workflow_id, transition_id)
    except WorkflowTransitionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transition not found") from exc


# ==================================================================
# Instances
# ==================================================================

@router.get("/{workflow_id}/instances", response_model=list[WorkflowInstanceRead])
async def list_instances(
    app_id: uuid.UUID,
    workflow_id: uuid.UUID,
    current_user: AuthDep,
    db: DbDep,
    record_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WorkflowInstanceRead]:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).list_instances(
        app_id, workflow_id, record_id=record_id, limit=limit
    )


@router.post("/{workflow_id}/instances", response_model=WorkflowInstanceRead,
             status_code=status.HTTP_201_CREATED)
async def start_instance(
    app_id: uuid.UUID, workflow_id: uuid.UUID, body: StartInstanceRequest,
    current_user: AuthDep, db: DbDep,
) -> WorkflowInstanceRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).start_instance(
            app_id, workflow_id, body, actor_id=current_user.user_id
        )
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    except WorkflowInstanceAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Workflow instance already exists for this record",
                    "detail": str(exc)},
        ) from exc
    except WorkflowTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/{workflow_id}/instances/{instance_id}", response_model=WorkflowInstanceRead)
async def get_instance(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
) -> WorkflowInstanceRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).get_instance(workflow_id, instance_id)
    except WorkflowInstanceNotFoundError as exc:
        raise _instance_not_found(exc) from exc


@router.get("/{workflow_id}/instances/{instance_id}/transitions",
            response_model=list[AvailableTransitionRead])
async def get_available_transitions(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
) -> list[AvailableTransitionRead]:
    """Return transitions the current user can execute from the instance's current state."""
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).get_available_transitions(
            app_id, workflow_id, instance_id,
            actor_roles=current_user.roles,
        )
    except (WorkflowNotFoundError, WorkflowInstanceNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found") from exc


@router.post("/{workflow_id}/instances/{instance_id}/transition",
             response_model=TransitionResponse)
async def execute_transition(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    body: TransitionRequest, current_user: AuthDep, db: DbDep,
) -> TransitionResponse:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).execute_transition(
            app_id=app_id,
            workflow_id=workflow_id,
            instance_id=instance_id,
            req=body,
            actor_id=current_user.user_id,
            actor_roles=current_user.roles,
        )
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    except WorkflowInstanceNotFoundError as exc:
        raise _instance_not_found(exc) from exc
    except WorkflowConcurrentModificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Concurrent transition detected — reload and retry",
                    "instance_id": str(exc.instance_id)},
        ) from exc
    except WorkflowTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.patch("/{workflow_id}/instances/{instance_id}/assign",
              response_model=WorkflowInstanceRead)
async def assign_instance(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    body: AssignInstanceRequest, current_user: AuthDep, db: DbDep,
) -> WorkflowInstanceRead:
    """Manually assign a user or group to a workflow instance."""
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).assign_instance(
            app_id, workflow_id, instance_id, body
        )
    except WorkflowInstanceNotFoundError as exc:
        raise _instance_not_found(exc) from exc


@router.post("/{workflow_id}/instances/{instance_id}/cancel",
             response_model=WorkflowInstanceRead)
async def cancel_instance(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    body: CancelInstanceRequest, current_user: AuthDep, db: DbDep,
) -> WorkflowInstanceRead:
    """
    Hard-cancel a running workflow instance.

    Sets state to __cancelled__ and closes the instance immediately.
    Only platform_admin or app_admin may cancel instances.
    """
    await _check_app(app_id, current_user, db)
    if not current_user.has_role("platform_admin", "app_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Cancellation requires platform_admin or app_admin role")
    try:
        return await WorkflowService(db).cancel_instance(
            app_id, workflow_id, instance_id,
            actor_id=current_user.user_id,
            reason=body.reason,
        )
    except WorkflowInstanceNotFoundError as exc:
        raise _instance_not_found(exc) from exc
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=str(exc)) from exc


# ==================================================================
# Approval chains (definition CRUD)
# ==================================================================

@router.get("/{workflow_id}/approval-chains", response_model=list[ApprovalChainDefRead])
async def list_approval_chains(
    app_id: uuid.UUID, workflow_id: uuid.UUID, current_user: AuthDep, db: DbDep
) -> list[ApprovalChainDefRead]:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).list_approval_chains(workflow_id)


@router.post("/{workflow_id}/approval-chains", response_model=ApprovalChainDefRead,
             status_code=status.HTTP_201_CREATED)
async def create_approval_chain(
    app_id: uuid.UUID, workflow_id: uuid.UUID,
    body: ApprovalChainDefCreate, current_user: AuthDep, db: DbDep,
) -> ApprovalChainDefRead:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_workflow(app_id, workflow_id)
    except WorkflowNotFoundError as exc:
        raise _wf_not_found(exc) from exc
    return await WorkflowService(db).create_approval_chain(workflow_id, body)


@router.patch("/{workflow_id}/approval-chains/{chain_id}", response_model=ApprovalChainDefRead)
async def update_approval_chain(
    app_id: uuid.UUID, workflow_id: uuid.UUID, chain_id: uuid.UUID,
    body: ApprovalChainDefUpdate, current_user: AuthDep, db: DbDep,
) -> ApprovalChainDefRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).update_approval_chain(workflow_id, chain_id, body)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found") from exc


@router.delete("/{workflow_id}/approval-chains/{chain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_approval_chain(
    app_id: uuid.UUID, workflow_id: uuid.UUID, chain_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
) -> None:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).delete_approval_chain(workflow_id, chain_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chain not found") from exc


# ==================================================================
# Approval chain instances
# ==================================================================

@router.get("/{workflow_id}/instances/{instance_id}/approval-chains",
            response_model=list[ApprovalChainInstanceRead])
async def list_chain_instances(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
) -> list[ApprovalChainInstanceRead]:
    await _check_app(app_id, current_user, db)
    return await WorkflowService(db).list_chain_instances(instance_id)


@router.post("/{workflow_id}/instances/{instance_id}/approval-chains/{chain_instance_id}/decide",
             response_model=ApprovalChainInstanceRead)
async def decide_chain_level(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    chain_instance_id: uuid.UUID,
    body: ApprovalDecisionRequest, current_user: AuthDep, db: DbDep,
) -> ApprovalChainInstanceRead:
    await _check_app(app_id, current_user, db)
    try:
        return await WorkflowService(db).decide_chain_level(
            chain_instance_id=chain_instance_id,
            actor_id=current_user.user_id,
            req=body,
            app_id=app_id,
        )
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WorkflowTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


# ==================================================================
# Transition log
# ==================================================================

@router.get("/{workflow_id}/instances/{instance_id}/log",
            response_model=list[TransitionLogRead])
async def get_transition_log(
    app_id: uuid.UUID, workflow_id: uuid.UUID, instance_id: uuid.UUID,
    current_user: AuthDep, db: DbDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[TransitionLogRead]:
    await _check_app(app_id, current_user, db)
    try:
        await WorkflowService(db).get_instance(workflow_id, instance_id)
    except WorkflowInstanceNotFoundError as exc:
        raise _instance_not_found(exc) from exc
    return await WorkflowService(db).list_transition_log(instance_id, limit=limit)
