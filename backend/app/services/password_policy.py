"""Password policy: persistence, history checks, expiry management."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password_policy import PasswordPolicyError, validate_password
from app.core.security import verify_password
from app.models.identity import PasswordHistory, PasswordPolicy
from app.schemas.auth import PasswordPolicyUpdate


class PasswordPolicyService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self) -> PasswordPolicy:
        result = await self._db.execute(select(PasswordPolicy).where(PasswordPolicy.id == 1))
        policy = result.scalar_one_or_none()
        if policy is None:
            policy = PasswordPolicy(id=1)
            self._db.add(policy)
            await self._db.flush()
        return policy

    async def update(self, data: PasswordPolicyUpdate) -> PasswordPolicy:
        policy = await self.get()
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(policy, field, value)
        policy.updated_at = datetime.now(UTC)
        await self._db.flush()
        return policy

    async def validate(self, password: str) -> None:
        """Run strength rules against the active policy. Raises PasswordPolicyError."""
        policy = await self.get()
        validate_password(password, policy=policy)

    async def check_history(self, user_id: uuid.UUID, new_password: str) -> None:
        """Raise PasswordPolicyError if new_password repeats a recent password."""
        policy = await self.get()
        if policy.history_depth == 0:
            return
        stmt = (
            select(PasswordHistory)
            .where(PasswordHistory.user_id == user_id)
            .order_by(PasswordHistory.created_at.desc())
            .limit(policy.history_depth)
        )
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        for row in rows:
            if verify_password(new_password, row.password_hash):
                raise PasswordPolicyError(
                    f"Нельзя использовать один из последних {policy.history_depth} паролей."
                )

    async def record(self, user_id: uuid.UUID, password_hash: str) -> None:
        """Save hash to history."""
        self._db.add(PasswordHistory(user_id=user_id, password_hash=password_hash))
        await self._db.flush()

    async def expiry_dates(self) -> tuple[datetime, datetime | None]:
        """Return (changed_at=now, expires_at). expires_at is None if policy has no expiry."""
        policy = await self.get()
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=policy.max_age_days) if policy.max_age_days > 0 else None
        return now, expires_at
