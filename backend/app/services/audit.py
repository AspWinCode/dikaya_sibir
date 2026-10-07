"""Audit log service — write and query immutable action log."""

import uuid
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.identity import User

logger = structlog.get_logger(__name__)


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        action: str,
        *,
        user_id: uuid.UUID | None = None,
        actor_email: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        level: str = "info",
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            user_id=user_id,
            actor_email=actor_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            level=level,
            ip_address=ip_address,
            user_agent=user_agent,
            details=details or {},
        )
        self._db.add(entry)
        try:
            await self._db.flush()
        except Exception:
            logger.exception("audit_log_write_failed", action=action)

    async def list_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        level: str | None = None,
        action: str | None = None,
        user_id: uuid.UUID | None = None,
        org_id: uuid.UUID | None = None,
        since: datetime | None = None,
    ) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
        if org_id:
            stmt = stmt.join(User, User.id == AuditLog.user_id).where(User.org_id == org_id)
        if level:
            stmt = stmt.where(AuditLog.level == level)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
