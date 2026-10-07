"""
ABACService — field-level access control enforcement.

Design:
  - open by default: no row = ALLOW
  - explicit deny: row with can_read=False or can_write=False = DENY
  - deny wins: if the caller holds roles A and B, and B denies read,
    then the field is not readable regardless of A

Public API consumed by record endpoints:
    abac = ABACService(db)
    restrictions = await abac.get_restrictions(entity_id, actor_roles)
    safe_payload = restrictions.filter_payload(record.payload)
    denied = restrictions.check_write(payload.keys())

Admin API (field permission CRUD) is exposed via endpoints/security.py.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security import FieldPermission
from app.schemas.security import (
    FieldPermissionBulkUpsert,
    FieldPermissionRead,
    FieldRestrictionsResponse,
)

logger = structlog.get_logger(__name__)


# ------------------------------------------------------------------
# Value object returned by get_restrictions()
# ------------------------------------------------------------------


@dataclass
class FieldRestrictions:
    entity_id: uuid.UUID
    denied_read: set[str] = field(default_factory=set)
    denied_write: set[str] = field(default_factory=set)
    # Fields with an explicit can_read=True row for one of the caller's
    # roles — used to unmask a sensitive field for roles that have been
    # deliberately granted access, without changing the "open by default"
    # rule for everything else (see RecordService / app.core.field_crypto).
    explicit_read_allow: set[str] = field(default_factory=set)

    def filter_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Strip fields the caller is not allowed to read."""
        if not self.denied_read:
            return payload
        return {k: v for k, v in payload.items() if k not in self.denied_read}

    def check_write(self, fields: Iterable[str]) -> list[str]:
        """Return the subset of fields the caller cannot write."""
        if not self.denied_write:
            return []
        return [f for f in fields if f in self.denied_write]

    def to_response(self) -> FieldRestrictionsResponse:
        return FieldRestrictionsResponse(
            entity_id=self.entity_id,
            denied_read=sorted(self.denied_read),
            denied_write=sorted(self.denied_write),
        )


# ------------------------------------------------------------------
# ABAC service
# ------------------------------------------------------------------


class ABACService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ---- Enforcement ----

    async def get_restrictions(
        self,
        entity_id: uuid.UUID,
        actor_roles: list[str],
    ) -> FieldRestrictions:
        """
        Load field permissions for all of the caller's roles and compute
        the union of denied fields (deny wins).

        Returns FieldRestrictions(denied_read=set, denied_write=set).
        An empty set means no restrictions for that direction.
        """
        if not actor_roles:
            return FieldRestrictions(entity_id=entity_id)

        result = await self._db.execute(
            select(FieldPermission).where(
                FieldPermission.entity_id == entity_id,
                FieldPermission.role_id.in_(actor_roles),
            )
        )
        rows = result.scalars().all()

        denied_read: set[str] = set()
        denied_write: set[str] = set()
        explicit_read_allow: set[str] = set()

        for row in rows:
            if not row.can_read:
                denied_read.add(row.field_name)
            else:
                explicit_read_allow.add(row.field_name)
            if not row.can_write:
                denied_write.add(row.field_name)

        return FieldRestrictions(
            entity_id=entity_id,
            denied_read=denied_read,
            denied_write=denied_write,
            explicit_read_allow=explicit_read_allow,
        )

    # ---- Admin CRUD ----

    async def list_permissions(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
    ) -> list[FieldPermissionRead]:
        result = await self._db.execute(
            select(FieldPermission)
            .where(
                FieldPermission.app_id == app_id,
                FieldPermission.entity_id == entity_id,
            )
            .order_by(FieldPermission.field_name, FieldPermission.role_id)
        )
        return [FieldPermissionRead.model_validate(r) for r in result.scalars()]

    async def bulk_upsert(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        data: FieldPermissionBulkUpsert,
    ) -> list[FieldPermissionRead]:
        """
        Full replacement of all field permissions for this entity.
        Uses DELETE + INSERT within the current transaction.
        """
        await self._db.execute(
            delete(FieldPermission).where(
                FieldPermission.app_id == app_id,
                FieldPermission.entity_id == entity_id,
            )
        )

        new_rows: list[FieldPermission] = []
        for item in data.permissions:
            perm = FieldPermission(
                app_id=app_id,
                entity_id=entity_id,
                field_name=item.field_name,
                role_id=item.role_id,
                can_read=item.can_read,
                can_write=item.can_write,
            )
            self._db.add(perm)
            new_rows.append(perm)

        await self._db.flush()
        logger.info("field_permissions_updated", entity_id=str(entity_id), count=len(new_rows))
        return [FieldPermissionRead.model_validate(r) for r in new_rows]

    async def delete_permission(
        self,
        app_id: uuid.UUID,
        entity_id: uuid.UUID,
        perm_id: uuid.UUID,
    ) -> None:
        result = await self._db.execute(
            select(FieldPermission).where(
                FieldPermission.id == perm_id,
                FieldPermission.app_id == app_id,
                FieldPermission.entity_id == entity_id,
            )
        )
        perm = result.scalar_one_or_none()
        if perm is None:
            return  # idempotent
        await self._db.delete(perm)
        await self._db.flush()
