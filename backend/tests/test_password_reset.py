"""Forgot/reset password flow — end to end against the real endpoints.

Email delivery is mocked (no real SMTP in CI); see DEPLOY.md for how to
verify real SMTP delivery on a deployed environment.
"""
import re
from urllib.parse import urlparse, parse_qs

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.identity import User


@pytest.fixture()
async def reset_user(db_session: AsyncSession) -> User:
    user = User(
        email="reset_test@example.com",
        display_name="Reset Tester",
        password_hash=hash_password("OldPassw0rd!"),
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _capture_reset_url(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Stub out SMTP and capture the reset_url each call would have sent."""
    captured: list[str] = []

    async def fake_send_password_reset_email(to, display_name, reset_url, db=None):
        captured.append(reset_url)
        return True

    monkeypatch.setattr(
        "app.services.email.send_password_reset_email", fake_send_password_reset_email
    )
    return captured


def _extract_token(reset_url: str) -> str:
    token = parse_qs(urlparse(reset_url).query)["token"][0]
    assert token
    return token


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forgot_password_is_neutral_for_unknown_email(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _capture_reset_url(monkeypatch)
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nobody@example.com"}
    )
    # Same 204 regardless of whether the account exists — no user enumeration.
    assert resp.status_code == 204
    assert captured == []  # and no email was actually sent


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_reset_end_to_end(
    client: AsyncClient, reset_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _capture_reset_url(monkeypatch)

    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": reset_user.email}
    )
    assert resp.status_code == 204
    assert len(captured) == 1
    token = _extract_token(captured[0])

    # New password must satisfy the password policy.
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "BrandNew1!Pass"},
    )
    assert resp.status_code == 204

    # Old password no longer works.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": "OldPassw0rd!"},
    )
    assert resp.status_code == 401

    # New password works.
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": reset_user.email, "password": "BrandNew1!Pass"},
    )
    assert resp.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reset_token_cannot_be_reused(
    client: AsyncClient, reset_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _capture_reset_url(monkeypatch)
    await client.post("/api/v1/auth/forgot-password", json={"email": reset_user.email})
    token = _extract_token(captured[0])

    first = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "FirstNew1!Pass"},
    )
    assert first.status_code == 204

    second = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "SecondNew1!Pass"},
    )
    assert second.status_code == 400
    assert "недействительна" in second.json()["detail"] or "истекла" in second.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reset_rejects_unknown_token(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "Whatever1!Pass"},
    )
    assert resp.status_code == 400


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reset_rejects_password_violating_policy(
    client: AsyncClient, reset_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _capture_reset_url(monkeypatch)
    await client.post("/api/v1/auth/forgot-password", json={"email": reset_user.email})
    token = _extract_token(captured[0])

    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "short"},
    )
    assert resp.status_code == 422
    # Token must still be usable afterwards — a rejected policy check must not burn it.
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": token, "new_password": "ValidPass1!"},
    )
    assert resp.status_code == 204


@pytest.mark.integration
@pytest.mark.asyncio
async def test_forgot_password_does_not_fail_the_request_when_smtp_is_down(
    client: AsyncClient, reset_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """send_email swallows SMTP errors; the user must still get the neutral
    204 response, never a 500 with a stack trace."""
    async def failing_send(*args, **kwargs):
        return False

    monkeypatch.setattr("app.services.email.send_email", failing_send)

    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": reset_user.email}
    )
    assert resp.status_code == 204
