from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="infra/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_ENV: Literal["development", "testing", "production"] = "development"
    APP_NAME: str = "No-Code Platform API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"  # noqa: S105 — dev default, must be overridden in prod
    # Base64-encoded 32-byte key for AES-256-GCM field-level encryption (ТЗ 3.13).
    # Dev default is fixed and public — production MUST override this or
    # every "sensitive" field's encryption is worthless (see app/core/field_crypto.py).
    FIELD_ENCRYPTION_KEY: str = "3o4Kp1P8h6bYFvQxzT9mWnR2cJdL7sAeUgXi0MoNqKw="

    # Database
    DATABASE_URL: PostgresDsn
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]

    # JWT — RS256
    JWT_PRIVATE_KEY: str = ""  # PEM, populated from env/secret
    JWT_PUBLIC_KEY: str = ""  # PEM, populated from env/secret
    JWT_ALGORITHM: str = "RS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    @field_validator("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", mode="before")
    @classmethod
    def normalize_pem(cls, v: str) -> str:
        # Allow single-line PEM in env files (newlines escaped as \n).
        if isinstance(v, str) and "\\n" in v:
            return v.replace("\\n", "\n")
        return v

    # S3 / MinIO
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"  # noqa: S105 — MinIO's own documented local-dev default
    S3_BUCKET_FILES: str = "nocode-files"
    S3_BUCKET_EXPORTS: str = "nocode-exports"
    S3_REGION: str = "us-east-1"

    # SMTP
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = False
    EMAIL_FROM: str = "noreply@nocode.local"

    # Seed (development bootstrap admin)
    SEED_ADMIN_EMAIL: str = (
        "admin@lesovik.app"  # must be valid RFC-5321 email (.local rejected by email-validator)
    )
    SEED_ADMIN_PASSWORD: str = "ChangeMe123!"  # noqa: S105 — placeholder seed default, not a real credential
    SEED_ADMIN_NAME: str = "Platform Admin"

    # CORS — comma-separated string; parse with cors_origins_list property
    CORS_ORIGINS: str = ""

    # Public frontend URL (used in password-reset emails)
    FRONTEND_URL: str = "http://localhost:5173/editor"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # ClamAV
    CLAMAV_HOST: str = "clamav"
    CLAMAV_PORT: int = 3310

    # Password policy
    PASSWORD_MIN_LENGTH: int = 10
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_DIGIT: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = True

    # Session timeout (minutes), configurable by admin via env
    SESSION_TIMEOUT_MINUTES: int = 30

    # LDAP / Active Directory
    LDAP_ENABLED: bool = False
    LDAP_URL: str = "ldap://localhost:389"
    LDAP_BIND_DN: str = ""
    LDAP_BIND_PASSWORD: str = ""
    LDAP_SEARCH_BASE: str = "dc=example,dc=com"

    # Яндекс ID OAuth 2.0
    YANDEX_CLIENT_ID: str = ""
    YANDEX_CLIENT_SECRET: str = ""
    YANDEX_REDIRECT_URI: str = "http://localhost:5173/editor/auth/yandex/callback"

    # VK ID OAuth 2.0
    VK_CLIENT_ID: str = ""
    VK_CLIENT_SECRET: str = ""
    VK_REDIRECT_URI: str = "http://localhost:5173/editor/auth/vk/callback"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Pagination
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    # Rate limiting (requests / minute per user)
    RATE_LIMIT_DEFAULT: int = 300
    RATE_LIMIT_AUTH: int = 20

    # OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    OTEL_SERVICE_NAME: str = "nocode-backend"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
