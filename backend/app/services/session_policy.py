"""Session policy: persistence and active-session queries."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import RefreshToken, SessionPolicy, User
from app.schemas.auth import SessionPolicyUpdate, SessionRead


class SessionPolicyService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self) -> SessionPolicy:
        result = await self._db.execute(select(SessionPolicy).where(SessionPolicy.id == 1))
        policy = result.scalar_one_or_none()
        if policy is None:
            policy = SessionPolicy(id=1)
            self._db.add(policy)
            await self._db.flush()
        return policy

    async def update(self, data: SessionPolicyUpdate) -> SessionPolicy:
        policy = await self.get()
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(policy, field, value)
        policy.updated_at = datetime.now(UTC)
        await self._db.flush()
        return policy

    async def list_sessions(
        self,
        user_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[SessionRead]:
        now = datetime.now(UTC)
        stmt = (
            select(RefreshToken, User.email, User.display_name)
            .join(User, User.id == RefreshToken.user_id)
            .where(RefreshToken.revoked.is_(False), RefreshToken.expires_at > now)
            .order_by(RefreshToken.created_at.desc())
            .limit(limit)
        )
        if user_id is not None:
            stmt = stmt.where(RefreshToken.user_id == user_id)
        result = await self._db.execute(stmt)
        rows = result.all()
        return [
            SessionRead(
                id=tok.id,
                user_id=tok.user_id,
                user_email=email,
                user_name=name,
                ip_address=tok.ip_address,
                user_agent=tok.user_agent,
                created_at=tok.created_at,
                last_activity_at=tok.last_activity_at,
                expires_at=tok.expires_at,
            )
            for tok, email, name in rows
        ]

    async def terminate(self, session_id: uuid.UUID) -> bool:
        result = await self._db.execute(
            select(RefreshToken).where(
                RefreshToken.id == session_id, RefreshToken.revoked.is_(False)
            )
        )
        tok = result.scalar_one_or_none()
        if tok is None:
            return False
        tok.revoked = True
        await self._db.flush()
        return True

    async def terminate_all_for_user(self, user_id: uuid.UUID) -> int:
        from sqlalchemy import update

        result = await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
            .returning(RefreshToken.id)
        )
        return len(result.all())
