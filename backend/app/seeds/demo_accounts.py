"""Demo accounts for the platform_admin/app-access authorization matrix
(ТЗ item 1) — lets someone click through every case in the acceptance
criteria without reading code: a platform_admin who is NOT a member of
any app (denied), a platform_admin WHO IS an explicit member (allowed,
per that role), an app owner, an app admin, an app viewer, and an
ordinary user with no access at all.

Run via: docker compose exec backend python -m app.seeds.demo_accounts
Idempotent — safe to run repeatedly; skips any account whose email
already exists. Targets the first non-archived app it finds (by name,
falling back to any app) rather than a hardcoded id, so it works on
any environment that already has at least one app.

Passwords are generated per run (never hardcoded, never committed) and
printed ONCE to stdout/log — write them down immediately. Every demo
account is created with must_change_password=True, so whoever uses one
has to set their own password on first login.
"""
import asyncio
import secrets

import structlog
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models.catalog import App, AppMember
from app.models.identity import Role, User, UserRole

configure_logging()
logger = structlog.get_logger(__name__)

TARGET_APP_NAME = "Дикая Сибирь"

# (email local-part, display name, global roles, AppMember role on the
# target app or None, one-line description shown in the printed summary)
DEMO_ACCOUNTS = [
    (
        "demo.platform_admin_no_app",
        "Демо: админ платформы (без доступа к приложению)",
        ["platform_admin"],
        None,
        "Должен открыть панель платформы, но НЕ должен открыть приложение.",
    ),
    (
        "demo.platform_admin_with_app",
        "Демо: админ платформы + явный доступ к приложению",
        ["platform_admin"],
        "owner",
        "Платформенная роль + явная выданная роль в приложении — доступ есть.",
    ),
    (
        "demo.app_owner",
        "Демо: владелец приложения",
        [],
        "owner",
        "Владелец своего приложения — полный доступ к нему, не админ платформы.",
    ),
    (
        "demo.app_admin",
        "Демо: администратор приложения",
        ["app_admin"],
        "admin",
        "Может управлять настройками и участниками приложения.",
    ),
    (
        "demo.app_viewer",
        "Демо: участник с ролью «просмотр»",
        [],
        "viewer",
        "Видит приложение и его данные, но не может их редактировать.",
    ),
    (
        "demo.stranger",
        "Демо: пользователь без доступа",
        [],
        None,
        "Обычный зарегистрированный пользователь — приложение не видит и не открывает.",
    ),
]


async def _find_target_app(session) -> App | None:
    result = await session.execute(select(App).where(App.name == TARGET_APP_NAME))
    app = result.scalar_one_or_none()
    if app is not None:
        return app
    result = await session.execute(select(App).order_by(App.created_at.asc()).limit(1))
    return result.scalar_one_or_none()


async def _ensure_role(session, role_id: str) -> None:
    if not await session.get(Role, role_id):
        session.add(Role(id=role_id, display_name=role_id, is_system=True))
        await session.flush()


async def run() -> None:
    logger.info("demo_seed_start")
    created: list[tuple[str, str, str]] = []  # email, password, description

    async with AsyncSessionLocal() as session:
        target_app = await _find_target_app(session)
        if target_app is None:
            logger.warning("demo_seed_no_app_found", detail="create an app first, then re-run")
            return

        domain = "demo.lesovik.local"
        for local_part, display_name, global_roles, app_role, description in DEMO_ACCOUNTS:
            email = f"{local_part}@{domain}"
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                logger.info("demo_account_exists", email=email)
                continue

            password = secrets.token_urlsafe(12)
            user = User(
                email=email,
                display_name=display_name,
                password_hash=hash_password(password),
                is_active=True,
                must_change_password=True,
            )
            session.add(user)
            await session.flush()

            for role_id in global_roles:
                await _ensure_role(session, role_id)
                session.add(UserRole(user_id=user.id, role_id=role_id))

            if app_role is not None:
                session.add(AppMember(app_id=target_app.id, user_id=user.id, role=app_role))

            created.append((email, password, description))
            logger.info("demo_account_created", email=email, app_role=app_role, global_roles=global_roles)

        await session.commit()

    if created:
        print("\n=== Demo accounts created (save these now — shown once) ===")
        print(f"Target app: {TARGET_APP_NAME!r}")
        for email, password, description in created:
            print(f"  {email}  /  {password}")
            print(f"    {description}")
        print("Each account must change its password on first login.\n")
    logger.info("demo_seed_done", created=len(created))


if __name__ == "__main__":
    asyncio.run(run())
