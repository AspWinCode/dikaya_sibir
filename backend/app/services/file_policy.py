"""File policy: platform-wide upload limits (ТЗ 3.7.1 / Приложение A)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import FilePolicy
from app.schemas.auth import FilePolicyUpdate

DEFAULT_ALLOWED_EXTENSIONS = [
    "pdf",
    "docx",
    "xlsx",
    "pptx",
    "odt",
    "txt",
    "rtf",
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "svg",
    "zip",
    "rar",
    "7z",
]


class FilePolicyService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self) -> FilePolicy:
        result = await self._db.execute(select(FilePolicy).where(FilePolicy.id == 1))
        policy = result.scalar_one_or_none()
        if policy is None:
            policy = FilePolicy(id=1, allowed_extensions=list(DEFAULT_ALLOWED_EXTENSIONS))
            self._db.add(policy)
            await self._db.flush()
        return policy

    async def update(self, data: FilePolicyUpdate) -> FilePolicy:
        policy = await self.get()
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(policy, field, value)
        policy.updated_at = datetime.now(UTC)
        await self._db.flush()
        return policy
