"""Seed script: loads reference roles and a bootstrap platform_admin user.

Run via: docker compose exec backend python -m app.seeds.run
Idempotent — safe to run repeatedly.

The admin credentials default to SEED_ADMIN_* settings (see app.core.config) and
can be overridden via environment / infra/.env.
"""

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models.identity import Role, User, UserRole

configure_logging()
logger = structlog.get_logger(__name__)

ROLES = [
    {"id": "platform_admin", "display_name": "Администратор платформы"},
    {"id": "org_admin", "display_name": "Администратор организации"},
    {"id": "app_builder", "display_name": "Конструктор приложений"},
    {"id": "app_admin", "display_name": "Администратор приложения"},
    {"id": "auditor", "display_name": "Аудитор"},
]

ADMIN_ROLES = ["platform_admin", "app_builder"]


async def _seed_roles(session: AsyncSession) -> None:
    existing = set((await session.execute(select(Role.id))).scalars().all())
    for role in ROLES:
        if role["id"] not in existing:
            session.add(Role(id=role["id"], display_name=role["display_name"], is_system=True))
    logger.info("seed_roles", total=len(ROLES), created=len(ROLES) - len(existing))


async def _seed_admin(session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.email == settings.SEED_ADMIN_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        logger.info("seed_admin_exists", email=settings.SEED_ADMIN_EMAIL, user_id=str(user.id))
        return

    user = User(
        email=settings.SEED_ADMIN_EMAIL,
        display_name=settings.SEED_ADMIN_NAME,
        password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    await session.flush()  # populate user.id
    for role_id in ADMIN_ROLES:
        session.add(UserRole(user_id=user.id, role_id=role_id))
    logger.info("seed_admin_created", email=settings.SEED_ADMIN_EMAIL, user_id=str(user.id))


async def run() -> None:
    logger.info("seed_start")
    async with AsyncSessionLocal() as session:
        await _seed_roles(session)
        await session.flush()
        await _seed_admin(session)
        await session.commit()
    logger.info("seed_done")


if __name__ == "__main__":
    asyncio.run(run())
