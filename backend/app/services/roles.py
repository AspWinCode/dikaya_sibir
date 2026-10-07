"""RoleService — custom role CRUD + resource permission management."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import AbacRule, ResourcePermission, Role
from app.schemas.security import (
    AbacRuleCreate,
    AbacRuleRead,
    AbacRuleUpdate,
    ResourcePermissionBulkUpsert,
    ResourcePermissionRead,
)
from app.schemas.users import RoleCreate, RoleRead, RoleUpdate
from app.services import abac
from app.services.audit import AuditService

logger = structlog.get_logger(__name__)


class RoleNotFoundError(Exception):
    pass


class RoleConflictError(Exception):
    pass


class RolePermissionError(Exception):
    pass


def _validate_conditions(condition_json: list) -> None:
    """Raise abac.AbacConditionError for the first unsupported condition —
    fail at save time rather than have the rule silently no-op every time
    it's evaluated (see app.services.abac)."""
    for cond in condition_json or []:
        abac.validate_condition(cond)


class RoleService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._audit = AuditService(db)

    # ── Role CRUD ──────────────────────────────────────────────────────────

    async def list_roles(self, actor_org_id: uuid.UUID | None = None) -> list[RoleRead]:
        stmt = select(Role).order_by(Role.is_system.desc(), Role.display_name)
        if actor_org_id is not None:
            stmt = stmt.where((Role.is_system.is_(True)) | (Role.org_id == actor_org_id))
        result = await self._db.execute(stmt)
        return [RoleRead.model_validate(r) for r in result.scalars()]

    async def create_role(
        self,
        data: RoleCreate,
        *,
        created_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        org_id: uuid.UUID | None = None,
    ) -> RoleRead:
        role_id = f"custom_{uuid.uuid4().hex[:12]}"
        role = Role(
            id=role_id,
            display_name=data.display_name,
            description=data.description,
            is_system=False,
            org_id=org_id,
        )
        self._db.add(role)
        await self._db.flush()

        await self._audit.log(
            action="role_created",
            resource_type="role",
            resource_id=role_id,
            level="info",
            user_id=created_by,
            actor_email=actor_email,
            details={"display_name": data.display_name},
        )
        logger.info("role_created", role_id=role_id, display_name=data.display_name)
        return RoleRead.model_validate(role)

    async def update_role(
        self,
        role_id: str,
        data: RoleUpdate,
        *,
        updated_by: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> RoleRead:
        role = await self._get_role(role_id)
        if role.is_system:
            raise RolePermissionError("System roles cannot be modified")

        changed: dict = {}
        if data.display_name is not None:
            role.display_name = data.display_name
            changed["display_name"] = data.display_name
        if data.description is not None:
            role.description = data.description
            changed["description"] = data.description

        await self._db.flush()
        await self._audit.log(
            action="role_updated",
            resource_type="role",
            resource_id=role_id,
            level="info",
            user_id=updated_by,
            actor_email=actor_email,
            details=changed,
        )
        return RoleRead.model_validate(role)

    async def delete_role(
        self,
        role_id: str,
        *,
        deleted_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_org_id: uuid.UUID | None = None,
    ) -> None:
        role = await self._get_role(role_id)
        if role.is_system:
            raise RolePermissionError("System roles cannot be deleted")
        if actor_org_id is not None and role.org_id != actor_org_id:
            raise RolePermissionError("Cannot delete role from another organisation")
        await self._db.delete(role)
        await self._db.flush()

        await self._audit.log(
            action="role_deleted",
            resource_type="role",
            resource_id=role_id,
            level="warn",
            user_id=deleted_by,
            actor_email=actor_email,
            details={"display_name": role.display_name},
        )
        logger.info("role_deleted", role_id=role_id)

    async def _get_role(self, role_id: str) -> Role:
        result = await self._db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()
        if role is None:
            raise RoleNotFoundError(f"Role {role_id!r} not found")
        return role

    # ── Resource permissions ───────────────────────────────────────────────

    async def list_resource_permissions(
        self,
        role_id: str | None = None,
        resource_type: str | None = None,
    ) -> list[ResourcePermissionRead]:
        stmt = select(ResourcePermission)
        if role_id:
            stmt = stmt.where(ResourcePermission.role_id == role_id)
        if resource_type:
            stmt = stmt.where(ResourcePermission.resource_type == resource_type)
        stmt = stmt.order_by(
            ResourcePermission.role_id,
            ResourcePermission.resource_type,
            ResourcePermission.resource_id,
        )
        result = await self._db.execute(stmt)
        return [ResourcePermissionRead.model_validate(r) for r in result.scalars()]

    async def bulk_upsert_resource_permissions(
        self,
        role_id: str,
        data: ResourcePermissionBulkUpsert,
        *,
        updated_by: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> list[ResourcePermissionRead]:
        await self._db.execute(
            delete(ResourcePermission).where(ResourcePermission.role_id == role_id)
        )
        rows: list[ResourcePermission] = []
        for item in data.permissions:
            perm = ResourcePermission(
                role_id=role_id,
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                action=item.action,
                allowed=item.allowed,
            )
            self._db.add(perm)
            rows.append(perm)
        await self._db.flush()

        await self._audit.log(
            action="resource_permissions_updated",
            resource_type="role",
            resource_id=role_id,
            level="info",
            user_id=updated_by,
            actor_email=actor_email,
            details={"count": len(rows)},
        )
        return [ResourcePermissionRead.model_validate(r) for r in rows]

    # ── ABAC rules ─────────────────────────────────────────────────────────

    async def list_abac_rules(
        self,
        role_id: str | None = None,
    ) -> list[AbacRuleRead]:
        stmt = select(AbacRule).order_by(AbacRule.priority.desc(), AbacRule.created_at)
        if role_id:
            stmt = stmt.where(AbacRule.role_id == role_id)
        result = await self._db.execute(stmt)
        return [AbacRuleRead.model_validate(r) for r in result.scalars()]

    async def create_abac_rule(
        self,
        data: AbacRuleCreate,
        *,
        created_by: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> AbacRuleRead:
        _validate_conditions(data.condition_json)
        rule = AbacRule(
            role_id=data.role_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            condition_json=data.condition_json,
            effect=data.effect,
            priority=data.priority,
            description=data.description,
            created_by=created_by,
        )
        self._db.add(rule)
        await self._db.flush()

        await self._audit.log(
            action="abac_rule_created",
            resource_type="abac_rule",
            resource_id=str(rule.id),
            level="info",
            user_id=created_by,
            actor_email=actor_email,
            details={
                "role_id": data.role_id,
                "resource_type": data.resource_type,
                "effect": data.effect,
            },
        )
        return AbacRuleRead.model_validate(rule)

    async def update_abac_rule(
        self,
        rule_id: uuid.UUID,
        data: AbacRuleUpdate,
        *,
        updated_by: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> AbacRuleRead:
        result = await self._db.execute(select(AbacRule).where(AbacRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule is None:
            raise RoleNotFoundError(f"ABAC rule {rule_id} not found")

        if data.condition_json is not None:
            _validate_conditions(data.condition_json)

        changed: dict = {}
        if data.resource_type is not None:
            rule.resource_type = data.resource_type
            changed["resource_type"] = data.resource_type
        if data.resource_id is not None:
            rule.resource_id = data.resource_id
            changed["resource_id"] = data.resource_id
        if data.condition_json is not None:
            rule.condition_json = data.condition_json
            changed["condition_json"] = data.condition_json
        if data.effect is not None:
            rule.effect = data.effect
            changed["effect"] = data.effect
        if data.priority is not None:
            rule.priority = data.priority
            changed["priority"] = data.priority
        if data.description is not None:
            rule.description = data.description
            changed["description"] = data.description

        await self._db.flush()
        await self._audit.log(
            action="abac_rule_updated",
            resource_type="abac_rule",
            resource_id=str(rule_id),
            level="info",
            user_id=updated_by,
            actor_email=actor_email,
            details=changed,
        )
        return AbacRuleRead.model_validate(rule)

    async def delete_abac_rule(
        self,
        rule_id: uuid.UUID,
        *,
        deleted_by: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> None:
        result = await self._db.execute(select(AbacRule).where(AbacRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule is None:
            return  # idempotent
        await self._db.delete(rule)
        await self._db.flush()

        await self._audit.log(
            action="abac_rule_deleted",
            resource_type="abac_rule",
            resource_id=str(rule_id),
            level="warn",
            user_id=deleted_by,
            actor_email=actor_email,
            details={"role_id": rule.role_id, "resource_type": rule.resource_type},
        )
