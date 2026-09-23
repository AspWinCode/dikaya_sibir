"""Shareable app invite links: create/revoke, preview, accept, sign up via link."""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password_policy import PasswordPolicyError
from app.core.security import hash_password
from app.models.catalog import App, AppInviteLink, AppMember
from app.models.identity import User
from app.schemas.auth import TokenPair
from app.schemas.invites import (
    InviteAcceptResult,
    InviteLinkCreate,
    InviteLinkCreated,
    InviteLinkRead,
    InvitePreview,
    InviteSignupRequest,
)
from app.services.apps import AppService
from app.services.audit import AuditService
from app.services.password_policy import PasswordPolicyService

logger = structlog.get_logger(__name__)


class InviteInvalidError(Exception):
    """Token unknown, revoked, expired or exhausted."""


class InviteSignupDisabledError(Exception):
    pass


class InviteConflictError(Exception):
    pass


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class InviteService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ---- Management (app owner/admin) ----

    async def _require_manager(self, app_id: uuid.UUID, actor_id: uuid.UUID, is_admin: bool) -> None:
        apps = AppService(self._db)
        await apps._fetch_app(app_id)
        if not is_admin:
            await apps._require_role(app_id, actor_id, {"owner", "admin"})

    async def create_link(
        self, app_id: uuid.UUID, data: InviteLinkCreate, actor_id: uuid.UUID, is_admin: bool
    ) -> InviteLinkCreated:
        await self._require_manager(app_id, actor_id, is_admin)
        token = secrets.token_urlsafe(32)
        link = AppInviteLink(
            app_id=app_id,
            token_hash=_hash(token),
            role=data.role,
            allow_signup=data.allow_signup,
            max_uses=data.max_uses,
            use_count=0,
            expires_at=_now() + timedelta(days=data.expires_in_days) if data.expires_in_days else None,
            created_by=actor_id,
        )
        self._db.add(link)
        await self._db.flush()
        await self._db.refresh(link)
        await AuditService(self._db).log(
            "app_invite_link_created",
            user_id=actor_id,
            resource_type="app",
            resource_id=str(app_id),
            level="info",
            details={"link_id": str(link.id), "role": data.role, "max_uses": data.max_uses},
        )
        return InviteLinkCreated(**InviteLinkRead.model_validate(link).model_dump(), token=token)

    async def list_links(self, app_id: uuid.UUID, actor_id: uuid.UUID, is_admin: bool) -> list[InviteLinkRead]:
        await self._require_manager(app_id, actor_id, is_admin)
        rows = await self._db.execute(
            select(AppInviteLink)
            .where(
                AppInviteLink.app_id == app_id,
                AppInviteLink.revoked_at.is_(None),
                or_(AppInviteLink.expires_at.is_(None), AppInviteLink.expires_at > _now()),
                or_(AppInviteLink.max_uses.is_(None), AppInviteLink.use_count < AppInviteLink.max_uses),
            )
            .order_by(AppInviteLink.created_at.desc())
        )
        return [InviteLinkRead.model_validate(r) for r in rows.scalars().all()]

    async def revoke_link(
        self, app_id: uuid.UUID, link_id: uuid.UUID, actor_id: uuid.UUID, is_admin: bool
    ) -> None:
        await self._require_manager(app_id, actor_id, is_admin)
        link = (
            await self._db.execute(
                select(AppInviteLink).where(AppInviteLink.id == link_id, AppInviteLink.app_id == app_id)
            )
        ).scalar_one_or_none()
        if link is None or link.revoked_at is not None:
            return
        link.revoked_at = _now()
        await self._db.flush()
        await AuditService(self._db).log(
            "app_invite_link_revoked",
            user_id=actor_id,
            resource_type="app",
            resource_id=str(app_id),
            level="info",
            details={"link_id": str(link_id)},
        )

    # ---- Public flow ----

    async def _get_valid(self, token: str) -> tuple[AppInviteLink, App]:
        row = (
            await self._db.execute(
                select(AppInviteLink, App)
                .join(App, App.id == AppInviteLink.app_id)
                .where(AppInviteLink.token_hash == _hash(token))
            )
        ).first()
        if row is None:
            raise InviteInvalidError("Invite not found")
        link, app = row
        if (
            link.revoked_at is not None
            or app.is_archived
            or (link.expires_at is not None and link.expires_at <= _now())
            or (link.max_uses is not None and link.use_count >= link.max_uses)
        ):
            raise InviteInvalidError("Invite expired or revoked")
        return link, app

    async def preview(self, token: str) -> InvitePreview:
        link, app = await self._get_valid(token)
        return InvitePreview(
            app_id=app.id,
            app_name=app.name,
            role=link.role,
            allow_signup=link.allow_signup,
            expires_at=link.expires_at,
        )

    async def _consume(self, link: AppInviteLink) -> None:
        """Atomically bump use_count; fails if the link was exhausted concurrently."""
        result = await self._db.execute(
            update(AppInviteLink)
            .where(
                AppInviteLink.id == link.id,
                or_(AppInviteLink.max_uses.is_(None), AppInviteLink.use_count < AppInviteLink.max_uses),
            )
            .values(use_count=AppInviteLink.use_count + 1)
            .returning(AppInviteLink.id)
        )
        if result.scalar_one_or_none() is None:
            raise InviteInvalidError("Invite exhausted")

    async def _grant(self, link: AppInviteLink, user_id: uuid.UUID) -> bool:
        """Add membership; returns False when the user was already a member."""
        existing = (
            await self._db.execute(
                select(AppMember).where(AppMember.app_id == link.app_id, AppMember.user_id == user_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False
        await self._consume(link)
        self._db.add(
            AppMember(app_id=link.app_id, user_id=user_id, role=link.role, granted_by=link.created_by)
        )
        await self._db.flush()
        return True

    async def accept(self, token: str, user_id: uuid.UUID, actor_email: str | None = None) -> InviteAcceptResult:
        link, app = await self._get_valid(token)
        added = await self._grant(link, user_id)
        if added:
            await AuditService(self._db).log(
                "app_invite_accepted",
                user_id=user_id,
                actor_email=actor_email,
                resource_type="app",
                resource_id=str(app.id),
                level="info",
                details={"link_id": str(link.id), "role": link.role},
            )
        return InviteAcceptResult(app_id=app.id, role=link.role, already_member=not added)

    async def signup(
        self,
        token: str,
        data: InviteSignupRequest,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        from app.services.auth import AuthService

        link, app = await self._get_valid(token)
        if not link.allow_signup:
            raise InviteSignupDisabledError("Signup via this link is disabled")

        try:
            await PasswordPolicyService(self._db).validate(data.password)
        except PasswordPolicyError as exc:
            raise ValueError(str(exc)) from exc

        exists = (await self._db.execute(select(User.id).where(User.email == data.email))).first()
        if exists:
            raise InviteConflictError("Email already registered")

        user = User(
            email=data.email,
            display_name=data.display_name,
            password_hash=hash_password(data.password),
            org_id=app.org_id,
            password_changed_at=_now(),
        )
        self._db.add(user)
        await self._db.flush()
        await self._grant(link, user.id)
        await self._db.refresh(user, ["roles"])

        logger.info("user_signed_up_via_invite", user_id=str(user.id), app_id=str(app.id))
        await AuditService(self._db).log(
            "user_signed_up_via_invite",
            user_id=user.id,
            actor_email=user.email,
            resource_type="app",
            resource_id=str(app.id),
            level="info",
            details={"link_id": str(link.id), "role": link.role},
            ip_address=ip,
        )
        return await AuthService(self._db)._issue_tokens(user, user_agent=user_agent, ip=ip)
