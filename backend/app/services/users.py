import base64
import secrets
import uuid
from datetime import UTC, datetime
from typing import ClassVar

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.password_policy import PasswordPolicyError
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole
from app.schemas.common import CursorPage
from app.schemas.users import (
    AuditLogRead,
    InviteUserRequest,
    UserCreate,
    UserListParams,
    UserRead,
    UserUpdate,
)
from app.services.audit import AuditService
from app.services.password_policy import PasswordPolicyService

logger = structlog.get_logger(__name__)


class UserNotFoundError(Exception):
    pass


class UserConflictError(Exception):
    pass


def _encode_cursor(user_id: uuid.UUID, created_at: datetime) -> str:
    raw = f"{created_at.isoformat()}|{user_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    raw = base64.urlsafe_b64decode(cursor.encode()).decode()
    ts, uid = raw.split("|", 1)
    return datetime.fromisoformat(ts), uuid.UUID(uid)


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_users(
        self,
        params: UserListParams,
        actor_org_id: uuid.UUID | None = None,
    ) -> CursorPage[UserRead]:
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .order_by(User.created_at.asc(), User.id.asc())
        )

        # org_admin sees only users within their organisation
        if actor_org_id is not None:
            stmt = stmt.where(User.org_id == actor_org_id)

        if params.is_active is not None:
            stmt = stmt.where(User.is_active == params.is_active)

        if params.role:
            stmt = stmt.join(User.user_roles).where(UserRole.role_id == params.role)

        if params.search:
            term = f"%{params.search}%"
            stmt = stmt.where(or_(User.email.ilike(term), User.display_name.ilike(term)))

        if params.cursor:
            cur_ts, cur_id = _decode_cursor(params.cursor)
            stmt = stmt.where(
                or_(
                    User.created_at > cur_ts,
                    (User.created_at == cur_ts) & (User.id > cur_id),
                )
            )

        stmt = stmt.limit(params.limit + 1)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()

        has_more = len(rows) > params.limit
        items = rows[: params.limit]
        next_cursor = _encode_cursor(items[-1].id, items[-1].created_at) if has_more else None

        return CursorPage(
            items=[UserRead.model_validate(u) for u in items],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def get_by_id(self, user_id: uuid.UUID) -> UserRead:
        user = await self._fetch_user(user_id)
        return UserRead.model_validate(user)

    async def create_user(
        self,
        data: UserCreate,
        granted_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_org_id: uuid.UUID | None = None,
    ) -> UserRead:
        # Validate password policy
        try:
            await PasswordPolicyService(self._db).validate(data.password)
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc

        # Check email uniqueness
        existing = await self._db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise UserConflictError(f"Email already registered: {data.email}")

        if actor_org_id is not None:
            await self._check_org_assignable_roles(data.roles, actor_org_id)

        user = User(
            email=data.email,
            display_name=data.display_name,
            password_hash=hash_password(data.password),
            org_id=actor_org_id,
        )
        self._db.add(user)
        await self._db.flush()

        if data.roles:
            await self._set_roles(user.id, data.roles, granted_by=granted_by)

        await self._db.flush()
        logger.info("user_created", user_id=str(user.id), email=data.email)
        await AuditService(self._db).log(
            "user_created",
            user_id=granted_by,
            actor_email=actor_email,
            resource_type="user",
            resource_id=str(user.id),
            level="info",
            details={"email": data.email, "roles": data.roles},
        )
        return await self.get_by_id(user.id)

    async def invite_user(
        self,
        data: InviteUserRequest,
        granted_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_org_id: uuid.UUID | None = None,
    ) -> tuple[UserRead, str]:
        """Create user with random password, return (user, temp_password)."""
        existing = await self._db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            raise UserConflictError(f"Email already registered: {data.email}")

        if actor_org_id is not None:
            await self._check_org_assignable_roles(data.roles, actor_org_id)

        temp_password = secrets.token_urlsafe(12)
        user = User(
            email=data.email,
            display_name=data.display_name,
            password_hash=hash_password(temp_password),
            org_id=actor_org_id,
            must_change_password=True,
        )
        self._db.add(user)
        await self._db.flush()

        if data.roles:
            await self._set_roles(user.id, data.roles, granted_by=granted_by)

        await self._db.flush()
        logger.info("user_invited", user_id=str(user.id), email=data.email)
        await AuditService(self._db).log(
            "user_invited",
            user_id=granted_by,
            actor_email=actor_email,
            resource_type="user",
            resource_id=str(user.id),
            level="info",
            details={"email": data.email, "roles": data.roles},
        )
        return await self.get_by_id(user.id), temp_password

    async def update_user(
        self,
        user_id: uuid.UUID,
        data: UserUpdate,
        updated_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_org_id: uuid.UUID | None = None,
    ) -> UserRead:
        user = await self._fetch_user(user_id)

        # org_admin can only manage users within their own org
        if actor_org_id is not None and user.org_id != actor_org_id:
            raise PermissionError("Cannot manage users outside your organisation")

        changed: dict[str, object] = {}

        if data.display_name is not None:
            user.display_name = data.display_name
            changed["display_name"] = data.display_name
        if data.is_active is not None:
            user.is_active = data.is_active
            changed["is_active"] = data.is_active
        if data.is_blocked is not None:
            user.is_blocked = data.is_blocked
            changed["is_blocked"] = data.is_blocked
        if data.roles is not None:
            if actor_org_id is not None:
                await self._check_org_assignable_roles(data.roles, actor_org_id)
            await self._set_roles(user_id, data.roles, granted_by=updated_by)
            changed["roles"] = data.roles

        await self._db.flush()
        logger.info("user_updated", user_id=str(user_id))
        level = "warn" if "roles" in changed or "is_active" in changed else "info"
        await AuditService(self._db).log(
            "user_updated",
            user_id=updated_by,
            actor_email=actor_email,
            resource_type="user",
            resource_id=str(user_id),
            level=level,
            details=changed,
        )
        return await self.get_by_id(user_id)

    async def set_password(
        self,
        user_id: uuid.UUID,
        new_password: str,
        set_by: uuid.UUID | None = None,
        actor_email: str | None = None,
    ) -> None:
        user = await self._fetch_user(user_id)
        try:
            await PasswordPolicyService(self._db).validate(new_password)
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc
        user.password_hash = hash_password(new_password)
        user.password_changed_at = datetime.now(UTC)
        await self._db.flush()
        logger.info("admin_set_password", user_id=str(user_id))
        await AuditService(self._db).log(
            "user_updated",
            user_id=set_by,
            actor_email=actor_email,
            resource_type="user",
            resource_id=str(user_id),
            level="warn",
            details={"action": "admin_password_set"},
        )

    async def delete_user(
        self,
        user_id: uuid.UUID,
        deleted_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_org_id: uuid.UUID | None = None,
    ) -> None:
        user = await self._fetch_user(user_id)
        if user.is_superuser:
            raise PermissionError("Cannot delete superuser")
        if actor_org_id is not None and user.org_id != actor_org_id:
            raise PermissionError("Cannot manage users outside your organisation")
        user.is_active = False
        await self._db.flush()
        logger.info("user_deactivated", user_id=str(user_id))
        await AuditService(self._db).log(
            "user_deactivated",
            user_id=deleted_by,
            actor_email=actor_email,
            resource_type="user",
            resource_id=str(user_id),
            level="warn",
        )

    async def hard_delete_user(
        self,
        user_id: uuid.UUID,
        deleted_by: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_org_id: uuid.UUID | None = None,
    ) -> None:
        from sqlalchemy import delete as sa_delete

        user = await self._fetch_user(user_id)
        if user.is_superuser:
            raise PermissionError("Cannot delete superuser")
        if actor_org_id is not None and user.org_id != actor_org_id:
            raise PermissionError("Cannot manage users outside your organisation")
        await AuditService(self._db).log(
            "user_hard_deleted",
            user_id=deleted_by,
            actor_email=actor_email,
            resource_type="user",
            resource_id=str(user_id),
            level="warn",
            details={"email": user.email, "display_name": user.display_name},
        )
        await self._db.execute(sa_delete(User).where(User.id == user_id))
        await self._db.flush()
        logger.info("user_hard_deleted", user_id=str(user_id))

    async def list_audit_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        level: str | None = None,
        action: str | None = None,
        org_id: uuid.UUID | None = None,
    ) -> list[AuditLogRead]:
        from app.services.audit import AuditService

        logs = await AuditService(self._db).list_logs(
            limit=limit, offset=offset, level=level, action=action, org_id=org_id
        )
        return [AuditLogRead.model_validate(e) for e in logs]

    async def get_roles(self) -> list[dict[str, str]]:
        result = await self._db.execute(select(Role).order_by(Role.id))
        return [{"id": r.id, "display_name": r.display_name} for r in result.scalars()]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _fetch_user(self, user_id: uuid.UUID) -> User:
        stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise UserNotFoundError(str(user_id))
        return user

    async def _set_roles(
        self, user_id: uuid.UUID, role_ids: list[str], granted_by: uuid.UUID | None
    ) -> None:
        # Validate role ids exist
        result = await self._db.execute(select(Role.id).where(Role.id.in_(role_ids)))
        found = set(result.scalars())
        invalid = set(role_ids) - found
        if invalid:
            raise ValueError(f"Unknown roles: {invalid}")

        # Delete old assignments
        existing = await self._db.execute(select(UserRole).where(UserRole.user_id == user_id))
        for ur in existing.scalars():
            await self._db.delete(ur)

        # Insert new ones
        for rid in role_ids:
            self._db.add(UserRole(user_id=user_id, role_id=rid, granted_by=granted_by))

    _ORG_ASSIGNABLE_ROLES: ClassVar[set[str]] = {
        "org_admin",
        "app_builder",
        "app_admin",
        "auditor",
    }

    async def _check_org_assignable_roles(
        self, role_ids: list[str], actor_org_id: uuid.UUID
    ) -> None:
        # System roles are always assignable; custom roles are assignable if
        # they belong to the org_admin's own org (custom roles are already
        # org-scoped, so this doesn't leak across orgs).
        non_system = set(role_ids) - self._ORG_ASSIGNABLE_ROLES
        if non_system:
            result = await self._db.execute(
                select(Role.id).where(Role.id.in_(non_system), Role.org_id == actor_org_id)
            )
            non_system -= set(result.scalars())
        forbidden = non_system
        if forbidden:
            raise PermissionError(f"Roles not assignable by org_admin: {forbidden}")
