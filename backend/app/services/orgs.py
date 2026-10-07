import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import Organisation, User, UserRole
from app.schemas.orgs import OrgCreate, OrgRead, OrgUpdate
from app.services.audit import AuditService

logger = structlog.get_logger(__name__)

PROTECTED_ROLES = {"platform_admin"}
ORG_ASSIGNABLE_ROLES = {
    "org_admin",
    "app_builder",
    "app_admin",
    "auditor",
}


class OrgNotFoundError(Exception):
    pass


class OrgConflictError(Exception):
    pass


class OrgPermissionError(Exception):
    pass


class OrgService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_orgs(self) -> list[OrgRead]:
        result = await self._db.execute(
            select(Organisation).order_by(Organisation.created_at.asc())
        )
        return [OrgRead.model_validate(o) for o in result.scalars()]

    async def get_org(self, org_id: uuid.UUID) -> OrgRead:
        org = await self._fetch(org_id)
        return OrgRead.model_validate(org)

    async def create_org(
        self,
        data: OrgCreate,
        created_by: uuid.UUID,
        actor_email: str | None = None,
    ) -> OrgRead:
        existing = await self._db.execute(
            select(Organisation).where(Organisation.slug == data.slug)
        )
        if existing.scalar_one_or_none():
            raise OrgConflictError(f"Slug already taken: {data.slug}")

        existing_user = await self._db.execute(select(User).where(User.email == data.admin_email))
        if existing_user.scalar_one_or_none():
            raise OrgConflictError(f"Email already registered: {data.admin_email}")

        org = Organisation(
            slug=data.slug,
            display_name=data.display_name,
            plan=data.plan,
            created_by=created_by,
        )
        self._db.add(org)
        await self._db.flush()

        admin = User(
            email=data.admin_email,
            display_name=data.admin_display_name,
            password_hash=hash_password(data.admin_password),
            org_id=org.id,
        )
        self._db.add(admin)
        await self._db.flush()

        self._db.add(UserRole(user_id=admin.id, role_id="org_admin", granted_by=created_by))
        await self._db.flush()

        logger.info("org_created", org_id=str(org.id), slug=org.slug, admin=data.admin_email)
        await AuditService(self._db).log(
            "org_created",
            user_id=created_by,
            actor_email=actor_email,
            resource_type="organisation",
            resource_id=str(org.id),
            level="info",
            details={"slug": org.slug, "admin_email": data.admin_email},
        )
        return OrgRead.model_validate(org)

    async def update_org(
        self,
        org_id: uuid.UUID,
        data: OrgUpdate,
        updated_by: uuid.UUID,
        actor_email: str | None = None,
    ) -> OrgRead:
        org = await self._fetch(org_id)
        changed: dict = {}

        if data.display_name is not None:
            org.display_name = data.display_name
            changed["display_name"] = data.display_name
        if data.plan is not None:
            org.plan = data.plan
            changed["plan"] = data.plan
        if data.is_active is not None:
            org.is_active = data.is_active
            changed["is_active"] = data.is_active

        await self._db.flush()
        logger.info("org_updated", org_id=str(org_id), changes=changed)
        await AuditService(self._db).log(
            "org_updated",
            user_id=updated_by,
            actor_email=actor_email,
            resource_type="organisation",
            resource_id=str(org_id),
            level="info",
            details=changed,
        )
        return OrgRead.model_validate(org)

    async def assert_role_assignable(self, role_ids: list[str]) -> None:
        """Raise OrgPermissionError if any role is not assignable by org_admin."""
        forbidden = set(role_ids) - ORG_ASSIGNABLE_ROLES
        if forbidden:
            raise OrgPermissionError(f"Roles not assignable by org_admin: {forbidden}")

    async def _fetch(self, org_id: uuid.UUID) -> Organisation:
        result = await self._db.execute(select(Organisation).where(Organisation.id == org_id))
        org = result.scalar_one_or_none()
        if org is None:
            raise OrgNotFoundError(str(org_id))
        return org
