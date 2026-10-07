"""Password policy validator."""

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.identity import PasswordPolicy


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str, *, policy: "PasswordPolicy") -> None:
    """Raise PasswordPolicyError if the password does not meet the given policy."""
    if len(password) < policy.min_length:
        raise PasswordPolicyError(f"Пароль должен содержать минимум {policy.min_length} символов.")
    if policy.require_uppercase and not re.search(r"[A-ZА-ЯЁ]", password):
        raise PasswordPolicyError("Пароль должен содержать хотя бы одну заглавную букву.")
    if policy.require_lowercase and not re.search(r"[a-zа-яё]", password):
        raise PasswordPolicyError("Пароль должен содержать хотя бы одну строчную букву.")
    if policy.require_digit and not re.search(r"\d", password):
        raise PasswordPolicyError("Пароль должен содержать хотя бы одну цифру.")
    if policy.require_special and not re.search(
        r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password
    ):
        raise PasswordPolicyError("Пароль должен содержать хотя бы один специальный символ.")
