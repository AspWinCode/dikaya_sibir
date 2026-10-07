import structlog
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthDep, DbDep
from app.core.config import settings
from app.core.rate_limit import limiter
from app.schemas.auth import (
    ChangePasswordRequest,
    FilePolicyRead,
    FilePolicyUpdate,
    ForgotPasswordRequest,
    LdapLoginRequest,
    LoginRequest,
    PasswordPolicyRead,
    PasswordPolicyUpdate,
    RefreshRequest,
    ResetPasswordRequest,
    SessionPolicyRead,
    SessionPolicyUpdate,
    TokenPair,
    TOTPSetupResponse,
    TOTPVerifyRequest,
    VkCallbackRequest,
    YandexCallbackRequest,
)
from app.services.auth import AuthError, AuthService

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _svc(db: AsyncSession) -> AuthService:
    return AuthService(db)


def _map_auth_error(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/login", response_model=TokenPair, summary="Password login (+ optional TOTP)")
@limiter.limit("10/minute")
async def login(req: LoginRequest, request: Request, db: DbDep) -> TokenPair:
    try:
        return await _svc(db).login(
            req,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.post("/refresh", response_model=TokenPair, summary="Rotate refresh token")
@limiter.limit("30/minute")
async def refresh(req: RefreshRequest, request: Request, db: DbDep) -> TokenPair:
    try:
        return await _svc(db).refresh(req.refresh_token)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke refresh token")
async def logout(req: RefreshRequest, db: DbDep) -> None:
    await _svc(db).logout(req.refresh_token)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke all sessions for current user",
)
async def logout_all(current_user: AuthDep, db: DbDep) -> None:
    await _svc(db).logout_all(current_user.user_id)


@router.post(
    "/forgot-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Request password reset email",
)
@limiter.limit("5/minute")
async def forgot_password(req: ForgotPasswordRequest, request: Request, db: DbDep) -> None:
    try:
        await _svc(db).request_password_reset(req)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Set new password using reset token",
)
@limiter.limit("10/minute")
async def reset_password(req: ResetPasswordRequest, request: Request, db: DbDep) -> None:
    try:
        await _svc(db).reset_password(req)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(req: ChangePasswordRequest, current_user: AuthDep, db: DbDep) -> None:
    try:
        await _svc(db).change_password(current_user.user_id, req)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


# ---- TOTP ----


@router.post("/totp/setup", response_model=TOTPSetupResponse, summary="Get TOTP provisioning URI")
async def totp_setup(current_user: AuthDep, db: DbDep) -> TOTPSetupResponse:
    from sqlalchemy import select

    from app.models.identity import User

    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        return await _svc(db).totp_setup(user)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.post(
    "/totp/enable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Confirm TOTP code and enable 2FA",
)
async def totp_enable(req: TOTPVerifyRequest, current_user: AuthDep, db: DbDep) -> None:
    from sqlalchemy import select

    from app.models.identity import User

    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        await _svc(db).totp_enable(user, req.code)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.post(
    "/totp/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable 2FA (requires valid TOTP code)",
)
async def totp_disable(req: TOTPVerifyRequest, current_user: AuthDep, db: DbDep) -> None:
    from sqlalchemy import select

    from app.models.identity import User

    result = await db.execute(select(User).where(User.id == current_user.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        await _svc(db).totp_disable(user, req.code)
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


# ---- LDAP ----


@router.post("/ldap-login", response_model=TokenPair, summary="LDAP/AD login")
@limiter.limit("10/minute")
async def ldap_login(req: LdapLoginRequest, request: Request, db: DbDep) -> TokenPair:
    try:
        return await _svc(db).ldap_login(
            req,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


@router.get("/ldap-status", summary="Return LDAP configuration status (no secrets)")
async def ldap_status(current_user: AuthDep) -> dict:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    return {
        "enabled": settings.LDAP_ENABLED,
        "url": settings.LDAP_URL if settings.LDAP_ENABLED else None,
        "search_base": settings.LDAP_SEARCH_BASE if settings.LDAP_ENABLED else None,
        "bind_dn": settings.LDAP_BIND_DN if settings.LDAP_ENABLED else None,
    }


@router.post("/ldap-test", summary="Test LDAP connection with current settings")
async def ldap_test(current_user: AuthDep) -> dict:
    if not current_user.has_role("platform_admin", "org_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    if not settings.LDAP_ENABLED:
        return {"ok": False, "error": "LDAP не включён (LDAP_ENABLED=false)"}
    try:
        import ldap3  # type: ignore[import-untyped]

        server = ldap3.Server(settings.LDAP_URL, get_info=ldap3.ALL, connect_timeout=5)
        conn = ldap3.Connection(
            server, settings.LDAP_BIND_DN, settings.LDAP_BIND_PASSWORD, auto_bind=True
        )
        conn.unbind()
        return {"ok": True, "message": f"Соединение с {settings.LDAP_URL} установлено"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---- Password policy ----


@router.get(
    "/password-policy", response_model=PasswordPolicyRead, summary="Get current password policy"
)
async def get_password_policy(db: DbDep) -> PasswordPolicyRead:
    from app.services.password_policy import PasswordPolicyService

    policy = await PasswordPolicyService(db).get()
    return PasswordPolicyRead.model_validate(policy)


@router.put(
    "/password-policy",
    response_model=PasswordPolicyRead,
    summary="Update password policy (admin only)",
)
async def update_password_policy(
    body: PasswordPolicyUpdate, current_user: AuthDep, db: DbDep
) -> PasswordPolicyRead:
    if not current_user.has_role("platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    from app.services.password_policy import PasswordPolicyService

    policy = await PasswordPolicyService(db).update(body)
    return PasswordPolicyRead.model_validate(policy)


# ---- Session policy ----


@router.get(
    "/session-policy", response_model=SessionPolicyRead, summary="Get current session policy"
)
async def get_session_policy(db: DbDep) -> SessionPolicyRead:
    from app.services.session_policy import SessionPolicyService

    policy = await SessionPolicyService(db).get()
    return SessionPolicyRead.model_validate(policy)


@router.put(
    "/session-policy",
    response_model=SessionPolicyRead,
    summary="Update session policy (admin only)",
)
async def update_session_policy(
    body: SessionPolicyUpdate, current_user: AuthDep, db: DbDep
) -> SessionPolicyRead:
    if not current_user.has_role("platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    from app.services.session_policy import SessionPolicyService

    policy = await SessionPolicyService(db).update(body)
    return SessionPolicyRead.model_validate(policy)


# ---- File policy ----


@router.get("/file-policy", response_model=FilePolicyRead, summary="Get current file upload policy")
async def get_file_policy(db: DbDep) -> FilePolicyRead:
    from app.services.file_policy import FilePolicyService

    policy = await FilePolicyService(db).get()
    return FilePolicyRead.model_validate(policy)


@router.put(
    "/file-policy", response_model=FilePolicyRead, summary="Update file upload policy (admin only)"
)
async def update_file_policy(
    body: FilePolicyUpdate, current_user: AuthDep, db: DbDep
) -> FilePolicyRead:
    if not current_user.has_role("platform_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
        )
    from app.services.file_policy import FilePolicyService

    policy = await FilePolicyService(db).update(body)
    return FilePolicyRead.model_validate(policy)


# ---- Яндекс ID ----


@router.get("/yandex", summary="Redirect to Yandex OAuth")
async def yandex_redirect() -> RedirectResponse:
    url = AuthService.yandex_auth_url()
    return RedirectResponse(url)


@router.post("/yandex/callback", response_model=TokenPair, summary="Yandex OAuth callback")
async def yandex_callback(req: YandexCallbackRequest, request: Request, db: DbDep) -> TokenPair:
    try:
        return await _svc(db).yandex_callback(
            req,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise _map_auth_error(exc) from exc


# ---- VK ID ----


@router.get("/vk", summary="Redirect to VK OAuth")
async def vk_redirect() -> RedirectResponse:
    url = AuthService.vk_auth_url()
    return RedirectResponse(url)


@router.post("/vk/callback", response_model=TokenPair, summary="VK OAuth callback")
async def vk_callback(req: VkCallbackRequest, request: Request, db: DbDep) -> TokenPair:
    try:
        return await _svc(db).vk_callback(
            req,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
    except AuthError as exc:
        raise _map_auth_error(exc) from exc
