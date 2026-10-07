from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)


class LdapLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class YandexCallbackRequest(BaseModel):
    code: str
    state: str | None = None


class VkCallbackRequest(BaseModel):
    code: str
    state: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 — the OAuth2 token-type literal, not a credential
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class TOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=1, max_length=128)


class PasswordPolicyRead(BaseModel):
    min_length: int
    require_uppercase: bool
    require_lowercase: bool
    require_digit: bool
    require_special: bool
    max_age_days: int
    history_depth: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class PasswordPolicyUpdate(BaseModel):
    min_length: int | None = Field(default=None, ge=6, le=128)
    require_uppercase: bool | None = None
    require_lowercase: bool | None = None
    require_digit: bool | None = None
    require_special: bool | None = None
    max_age_days: int | None = Field(default=None, ge=0, le=3650)
    history_depth: int | None = Field(default=None, ge=0, le=24)


class SessionPolicyRead(BaseModel):
    timeout_minutes: int
    max_concurrent_sessions: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class SessionPolicyUpdate(BaseModel):
    timeout_minutes: int | None = Field(default=None, ge=1, le=10080)  # max 7 days
    max_concurrent_sessions: int | None = Field(default=None, ge=0, le=100)  # 0 = unlimited


class FilePolicyRead(BaseModel):
    max_file_size_mb: int
    max_files_per_record: int
    allowed_extensions: list[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class FilePolicyUpdate(BaseModel):
    max_file_size_mb: int | None = Field(default=None, ge=1, le=500)
    max_files_per_record: int | None = Field(default=None, ge=1, le=1000)
    allowed_extensions: list[str] | None = Field(default=None, min_length=1)

    @field_validator("allowed_extensions")
    @classmethod
    def _normalize_extensions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = {ext.strip().lower().lstrip(".") for ext in value}
        normalized.discard("")
        if not normalized:
            raise ValueError("allowed_extensions must contain at least one extension")
        return sorted(normalized)


import uuid as _uuid  # noqa: E402


class SessionRead(BaseModel):
    id: _uuid.UUID
    user_id: _uuid.UUID
    user_email: str | None = None
    user_name: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime
    last_activity_at: datetime | None = None
    expires_at: datetime

    model_config = {"from_attributes": True}
