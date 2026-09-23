import hashlib
import secrets
import uuid
from datetime import UTC, datetime

import pyotp
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import auth_attempts, token_refreshes
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.identity import PasswordResetToken, RefreshToken, User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LdapLoginRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenPair,
    TOTPSetupResponse,
    VkCallbackRequest,
    YandexCallbackRequest,
)
from app.services.audit import AuditService

logger = structlog.get_logger(__name__)

_ACCESS_EXPIRES = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


class AuthError(Exception):
    """Raised for business-logic auth failures (mapped to 401/403 in endpoints)."""

    def __init__(self, detail: str, status_code: int = 401) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(
        self,
        req: LoginRequest,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        try:
            user = await self._get_active_user_by_email(req.email)
        except AuthError:
            auth_attempts.labels(result="wrong_password").inc()
            raise

        if not user.password_hash or not verify_password(req.password, user.password_hash):
            logger.warning("login_failed_bad_password", email=req.email)
            auth_attempts.labels(result="wrong_password").inc()
            raise AuthError("Invalid credentials")

        # Check password expiry
        if user.password_expires_at and datetime.now(UTC) > user.password_expires_at:
            raise AuthError("Срок действия пароля истёк. Измените пароль.", status_code=403)

        if user.totp_enabled:
            if not req.totp_code:
                auth_attempts.labels(result="totp_required").inc()
                raise AuthError("TOTP code required", status_code=403)
            if not self._verify_totp(user.totp_secret, req.totp_code):  # type: ignore[arg-type]
                logger.warning("login_failed_bad_totp", user_id=str(user.id))
                auth_attempts.labels(result="totp_invalid").inc()
                raise AuthError("Invalid TOTP code", status_code=403)

        # Update last_login_at
        await self._db.execute(
            update(User)
            .where(User.id == user.id)
            .values(last_login_at=datetime.now(UTC))
        )

        auth_attempts.labels(result="success").inc()
        logger.info("login_success", user_id=str(user.id))
        await AuditService(self._db).log(
            "login",
            user_id=user.id,
            actor_email=user.email,
            resource_type="user",
            resource_id=str(user.id),
            level="info",
            ip_address=ip,
            user_agent=user_agent,
        )
        return await self._issue_tokens(user, user_agent=user_agent, ip=ip)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refresh(self, raw_refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(raw_refresh_token)
        except Exception as exc:
            token_refreshes.labels(result="expired").inc()
            raise AuthError("Invalid refresh token") from exc

        if payload.get("type") != "refresh":
            token_refreshes.labels(result="expired").inc()
            raise AuthError("Not a refresh token")

        token_hash = _hash_token(raw_refresh_token)
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(UTC),
        )
        result = await self._db.execute(stmt)
        db_token = result.scalar_one_or_none()

        if db_token is None:
            token_refreshes.labels(result="revoked").inc()
            raise AuthError("Refresh token not found or revoked")

        # Check inactivity timeout
        from app.services.session_policy import SessionPolicyService
        from datetime import timedelta
        policy = await SessionPolicyService(self._db).get()
        if policy.timeout_minutes > 0:
            last = db_token.last_activity_at or db_token.created_at
            deadline = last + timedelta(minutes=policy.timeout_minutes)
            if datetime.now(UTC) > deadline:
                db_token.revoked = True
                await self._db.flush()
                token_refreshes.labels(result="idle_timeout").inc()
                raise AuthError("Session expired due to inactivity", status_code=401)

        # Rotate: revoke old, issue new pair; update activity
        db_token.revoked = True
        await self._db.flush()

        user = await self._get_active_user_by_id(db_token.user_id)
        token_refreshes.labels(result="success").inc()
        logger.info("token_refreshed", user_id=str(user.id))
        return await self._issue_tokens(user)

    # ------------------------------------------------------------------
    # Logout (revoke specific token or all)
    # ------------------------------------------------------------------
    async def logout(self, raw_refresh_token: str) -> None:
        token_hash = _hash_token(raw_refresh_token)
        await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )

    async def logout_all(self, user_id: uuid.UUID) -> None:
        await self._db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))
            .values(revoked=True)
        )

    # ------------------------------------------------------------------
    # Change password
    # ------------------------------------------------------------------
    async def change_password(self, user_id: uuid.UUID, req: ChangePasswordRequest) -> None:
        from app.services.password_policy import PasswordPolicyService
        from app.core.password_policy import PasswordPolicyError

        user = await self._get_active_user_by_id(user_id)
        if not user.password_hash or not verify_password(req.current_password, user.password_hash):
            raise AuthError("Current password is incorrect", status_code=403)

        pps = PasswordPolicyService(self._db)
        try:
            await pps.validate(req.new_password)
            await pps.check_history(user_id, req.new_password)
        except PasswordPolicyError as exc:
            raise AuthError(str(exc), status_code=422) from exc

        new_hash = hash_password(req.new_password)
        changed_at, expires_at = await pps.expiry_dates()
        await self._db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                password_hash=new_hash,
                password_changed_at=changed_at,
                password_expires_at=expires_at,
                must_change_password=False,
            )
        )
        await pps.record(user_id, new_hash)
        await self.logout_all(user_id)
        logger.info("password_changed", user_id=str(user_id))

    # ------------------------------------------------------------------
    # Forgot / reset password
    # ------------------------------------------------------------------
    async def request_password_reset(self, req: ForgotPasswordRequest) -> None:
        from datetime import timedelta
        from app.services.email import send_password_reset_email

        result = await self._db.execute(
            select(User).where(User.email == req.email, User.is_active.is_(True))
        )
        user = result.scalar_one_or_none()
        if user is None:
            # Silent — don't reveal whether the email exists
            return

        raw_token = secrets.token_urlsafe(32)
        token_hash = _hash_token(raw_token)
        expires_at = datetime.now(UTC) + timedelta(hours=1)

        self._db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        ))
        await self._db.flush()

        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
        await send_password_reset_email(
            to=user.email, display_name=user.display_name, reset_url=reset_url, db=self._db
        )
        logger.info("password_reset_requested", user_id=str(user.id))

    async def reset_password(self, req: ResetPasswordRequest) -> None:
        from app.core.password_policy import PasswordPolicyError
        from app.services.password_policy import PasswordPolicyService

        token_hash = _hash_token(req.token)
        result = await self._db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash,
                PasswordResetToken.used.is_(False),
                PasswordResetToken.expires_at > datetime.now(UTC),
            )
        )
        reset_token = result.scalar_one_or_none()
        if reset_token is None:
            raise AuthError("Ссылка недействительна или истекла", status_code=400)

        pps = PasswordPolicyService(self._db)
        try:
            await pps.validate(req.new_password)
            await pps.check_history(reset_token.user_id, req.new_password)
        except PasswordPolicyError as exc:
            raise AuthError(str(exc), status_code=422) from exc

        new_hash = hash_password(req.new_password)
        changed_at, expires_at = await pps.expiry_dates()
        await self._db.execute(
            update(User)
            .where(User.id == reset_token.user_id)
            .values(
                password_hash=new_hash,
                password_changed_at=changed_at,
                password_expires_at=expires_at,
                must_change_password=False,
            )
        )
        await pps.record(reset_token.user_id, new_hash)
        await self._db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.id == reset_token.id)
            .values(used=True)
        )
        await self.logout_all(reset_token.user_id)
        logger.info("password_reset_completed", user_id=str(reset_token.user_id))

    # ------------------------------------------------------------------
    # TOTP setup / enable / disable
    # ------------------------------------------------------------------
    async def totp_setup(self, user: User) -> TOTPSetupResponse:
        secret = pyotp.random_base32()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="No-Code Platform"
        )
        # Persist secret (not yet enabled — user must verify first)
        await self._db.execute(
            update(User).where(User.id == user.id).values(totp_secret=secret)
        )
        return TOTPSetupResponse(secret=secret, provisioning_uri=uri)

    async def totp_enable(self, user: User, code: str) -> None:
        if not user.totp_secret:
            raise AuthError("TOTP not configured", status_code=400)
        if not self._verify_totp(user.totp_secret, code):
            raise AuthError("Invalid TOTP code", status_code=403)
        await self._db.execute(
            update(User).where(User.id == user.id).values(totp_enabled=True)
        )

    async def totp_disable(self, user: User, code: str) -> None:
        if not user.totp_enabled or not user.totp_secret:
            raise AuthError("TOTP not enabled", status_code=400)
        if not self._verify_totp(user.totp_secret, code):
            raise AuthError("Invalid TOTP code", status_code=403)
        await self._db.execute(
            update(User)
            .where(User.id == user.id)
            .values(totp_secret=None, totp_enabled=False)
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _issue_tokens(
        self,
        user: User,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        from app.services.session_policy import SessionPolicyService

        now = datetime.now(UTC)
        access = create_access_token(
            user.id, user.role_ids, org_id=user.org_id, email=user.email,
            must_change_password=user.must_change_password,
        )
        refresh = create_refresh_token(user.id)

        expires_at = datetime.fromtimestamp(
            now.timestamp() + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, tz=UTC
        )
        db_token = RefreshToken(
            user_id=user.id,
            token_hash=_hash_token(refresh),
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip,
            last_activity_at=now,
        )
        self._db.add(db_token)
        await self._db.flush()

        # Enforce concurrent session limit (revoke oldest if over limit)
        policy = await SessionPolicyService(self._db).get()
        if policy.max_concurrent_sessions > 0:
            stmt = (
                select(RefreshToken)
                .where(
                    RefreshToken.user_id == user.id,
                    RefreshToken.revoked.is_(False),
                    RefreshToken.expires_at > now,
                )
                .order_by(RefreshToken.created_at.asc())
            )
            result = await self._db.execute(stmt)
            active = result.scalars().all()
            # active includes the newly added token (already flushed)
            overflow = len(active) - policy.max_concurrent_sessions
            for old_tok in active[:overflow]:
                old_tok.revoked = True
            if overflow > 0:
                await self._db.flush()

        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=_ACCESS_EXPIRES,
        )

    async def _get_active_user_by_email(self, email: str) -> User:
        stmt = select(User).where(User.email == email, User.is_active.is_(True))
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise AuthError("Invalid credentials")
        if user.is_blocked:
            raise AuthError("Account is blocked", status_code=403)
        return user

    async def _get_active_user_by_id(self, user_id: uuid.UUID) -> User:
        stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise AuthError("User not found or inactive")
        return user

    # ------------------------------------------------------------------
    # LDAP login
    # ------------------------------------------------------------------
    async def ldap_login(
        self,
        req: LdapLoginRequest,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        if not settings.LDAP_ENABLED:
            raise AuthError("LDAP authentication is not enabled", status_code=400)

        from app.core.ldap_auth import LdapAuthError, LdapClient

        client = LdapClient(
            settings.LDAP_URL,
            settings.LDAP_BIND_DN,
            settings.LDAP_BIND_PASSWORD,
            settings.LDAP_SEARCH_BASE,
        )
        try:
            ldap_user = client.authenticate(req.email, req.password)
        except LdapAuthError as exc:
            auth_attempts.labels(result="ldap_failed").inc()
            raise AuthError("LDAP authentication failed") from exc

        # Find or create local user
        stmt = select(User).where(User.email == req.email)
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            from app.core.security import hash_password as _hp
            user = User(
                email=req.email,
                display_name=ldap_user["display_name"],
                password_hash=_hp(secrets.token_urlsafe(32)),
            )
            self._db.add(user)
            await self._db.flush()
        elif not user.is_active:
            raise AuthError("Account is deactivated")

        await self._db.execute(
            update(User).where(User.id == user.id).values(last_login_at=datetime.now(UTC))
        )
        auth_attempts.labels(result="ldap_success").inc()
        await AuditService(self._db).log(
            "login_ldap", user_id=user.id, actor_email=user.email,
            level="info", ip_address=ip, user_agent=user_agent,
        )
        return await self._issue_tokens(user, user_agent=user_agent, ip=ip)

    # ------------------------------------------------------------------
    # Яндекс ID OAuth
    # ------------------------------------------------------------------
    @staticmethod
    def yandex_auth_url() -> str:
        from urllib.parse import urlencode
        params = {
            "response_type": "code",
            "client_id": settings.YANDEX_CLIENT_ID,
            "redirect_uri": settings.YANDEX_REDIRECT_URI,
        }
        return "https://oauth.yandex.ru/authorize?" + urlencode(params)

    async def yandex_callback(
        self,
        req: YandexCallbackRequest,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        import httpx

        if not settings.YANDEX_CLIENT_ID:
            raise AuthError("Yandex OAuth is not configured", status_code=400)

        # Exchange code for token
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth.yandex.ru/token",
                data={
                    "grant_type": "authorization_code",
                    "code": req.code,
                    "client_id": settings.YANDEX_CLIENT_ID,
                    "client_secret": settings.YANDEX_CLIENT_SECRET,
                    "redirect_uri": settings.YANDEX_REDIRECT_URI,
                },
            )
        if token_resp.status_code != 200:
            raise AuthError("Failed to exchange Yandex code for token")
        access_token = token_resp.json().get("access_token")

        # Get user info
        async with httpx.AsyncClient() as client:
            info_resp = await client.get(
                "https://login.yandex.ru/info",
                headers={"Authorization": f"OAuth {access_token}"},
            )
        if info_resp.status_code != 200:
            raise AuthError("Failed to fetch Yandex user info")
        info = info_resp.json()
        email: str = info.get("default_email") or info.get("login") + "@yandex.ru"
        display_name: str = info.get("display_name") or info.get("real_name") or email

        # Find or create local user
        stmt = select(User).where(User.email == email)
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                display_name=display_name,
                password_hash=None,
            )
            self._db.add(user)
            await self._db.flush()
        elif not user.is_active:
            raise AuthError("Account is deactivated")

        await self._db.execute(
            update(User).where(User.id == user.id).values(last_login_at=datetime.now(UTC))
        )
        auth_attempts.labels(result="yandex_success").inc()
        await AuditService(self._db).log(
            "login_yandex", user_id=user.id, actor_email=user.email,
            level="info", ip_address=ip, user_agent=user_agent,
        )
        return await self._issue_tokens(user, user_agent=user_agent, ip=ip)

    # ------------------------------------------------------------------
    # VK ID OAuth
    # ------------------------------------------------------------------
    @staticmethod
    def vk_auth_url() -> str:
        from urllib.parse import urlencode
        params = {
            "client_id": settings.VK_CLIENT_ID,
            "redirect_uri": settings.VK_REDIRECT_URI,
            "scope": "email",
            "response_type": "code",
            "v": "5.199",
        }
        return "https://oauth.vk.com/authorize?" + urlencode(params)

    async def vk_callback(
        self,
        req: VkCallbackRequest,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> TokenPair:
        import httpx

        if not settings.VK_CLIENT_ID:
            raise AuthError("VK OAuth is not configured", status_code=400)

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_resp = await client.get(
                "https://oauth.vk.com/access_token",
                params={
                    "client_id": settings.VK_CLIENT_ID,
                    "client_secret": settings.VK_CLIENT_SECRET,
                    "redirect_uri": settings.VK_REDIRECT_URI,
                    "code": req.code,
                },
            )
        if token_resp.status_code != 200 or "error" in token_resp.json():
            raise AuthError("Failed to exchange VK code for token")

        token_data = token_resp.json()
        vk_access_token: str = token_data["access_token"]
        vk_user_id: int = token_data["user_id"]
        email: str = token_data.get("email") or f"vk_{vk_user_id}@vk.com"

        # Get user profile
        async with httpx.AsyncClient() as client:
            info_resp = await client.get(
                "https://api.vk.com/method/users.get",
                params={
                    "user_ids": vk_user_id,
                    "fields": "first_name,last_name",
                    "access_token": vk_access_token,
                    "v": "5.199",
                },
            )
        display_name = email
        if info_resp.status_code == 200:
            users = info_resp.json().get("response", [])
            if users:
                u = users[0]
                display_name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() or email

        # Find or create local user
        stmt = select(User).where(User.email == email)
        result = await self._db.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                display_name=display_name,
                password_hash=None,
            )
            self._db.add(user)
            await self._db.flush()
        elif not user.is_active:
            raise AuthError("Account is deactivated")

        await self._db.execute(
            update(User).where(User.id == user.id).values(last_login_at=datetime.now(UTC))
        )
        auth_attempts.labels(result="vk_success").inc()
        await AuditService(self._db).log(
            "login_vk", user_id=user.id, actor_email=user.email,
            level="info", ip_address=ip, user_agent=user_agent,
        )
        return await self._issue_tokens(user, user_agent=user_agent, ip=ip)

    @staticmethod
    def _verify_totp(secret: str, code: str) -> bool:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
