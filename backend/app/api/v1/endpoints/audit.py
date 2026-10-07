"""Audit log API — read-only access to the immutable action journal."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, DbDep
from app.schemas.audit import AuditLogRead
from app.services.audit import AuditService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    current_user: AuthDep,
    db: DbDep,
    level: str | None = Query(default=None, description="Filter by level: info, warning, error"),
    action: str | None = Query(default=None, description="Filter by action name"),
    user_id: uuid.UUID | None = Query(default=None, description="Filter by actor user ID"),
    since: datetime | None = Query(
        default=None, description="Return entries after this timestamp (ISO 8601)"
    ),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogRead]:
    """
    Query the immutable audit log. Requires platform_admin role.

    Supports filtering by level, action, user_id, and time range.
    """
    if not current_user.has_role("platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit log access requires platform_admin role",
        )

    entries = await AuditService(db).list_logs(
        limit=limit,
        offset=offset,
        level=level,
        action=action,
        user_id=user_id,
        since=since,
    )
    return [AuditLogRead.model_validate(e) for e in entries]
