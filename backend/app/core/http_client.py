"""
Outbound HTTP client for webhook delivery.

Features:
  - Sync httpx (safe inside Celery workers that use asyncio.run for DB only)
  - HMAC-SHA256 request signing
  - Standard Lesovik headers injected automatically
  - Configurable timeout per subscription
  - SSRF guard: resolves the hostname and refuses to call private/loopback/
    link-local/reserved addresses (blocks the cloud metadata endpoint too).
    Applied to every outbound call — both admin-configured webhook
    subscriptions and ad-hoc `call_webhook` rule actions authored by
    app builders, who are a lower-trust audience than platform admins.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import time
from typing import Any
from urllib.parse import urlsplit

import httpx


class UnsafeUrlError(Exception):
    """Raised when a target URL resolves to a non-public address."""


def assert_url_is_safe(url: str) -> None:
    """
    Reject URLs that are not plain http(s) or that resolve to a private,
    loopback, link-local, reserved, or multicast address — this closes off
    SSRF against internal infra (postgres/redis/minio/backend containers)
    and the cloud metadata endpoint (169.254.169.254) via user-authored
    webhook targets.

    Raises UnsafeUrlError with a human-readable reason on rejection.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"unsupported scheme {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("missing host")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"DNS resolution failed: {exc}") from None

    if not infos:
        raise UnsafeUrlError("DNS resolution returned no addresses")

    for info in infos:
        raw_ip = info[4][0]
        ip = ipaddress.ip_address(raw_ip)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeUrlError(f"{host!r} resolves to non-public address {raw_ip}")


# ------------------------------------------------------------------
# HMAC signing
# ------------------------------------------------------------------


def compute_signature(secret: str, body: bytes) -> str:
    """Return 'sha256=<hex>' HMAC signature over the raw request body."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def generate_secret() -> str:
    """Generate a new random 32-byte hex webhook signing secret."""
    return secrets.token_hex(32)


# ------------------------------------------------------------------
# Event pattern matching
# ------------------------------------------------------------------


def matches_event(pattern: str, event_type: str) -> bool:
    """
    Check whether an event_type matches a subscription pattern.

      "*"           → matches everything
      "record.*"    → matches "record.created", "record.updated", …
      "record.created" → exact match only
    """
    if pattern == "*":
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return event_type == prefix or event_type.startswith(f"{prefix}.")
    return pattern == event_type


def subscription_matches(events_filter: list[str], event_type: str) -> bool:
    """Return True if any pattern in the filter list matches event_type."""
    return any(matches_event(p, event_type) for p in events_filter)


# ------------------------------------------------------------------
# Delivery
# ------------------------------------------------------------------


class DeliveryResult:
    __slots__ = ("error", "response_body", "status_code", "success")

    def __init__(
        self,
        success: bool,
        status_code: int | None = None,
        response_body: str | None = None,
        error: str | None = None,
    ) -> None:
        self.success = success
        self.status_code = status_code
        self.response_body = response_body
        self.error = error


def deliver(
    *,
    target_url: str,
    payload: dict[str, Any],
    event_type: str,
    delivery_id: str,
    secret: str,
    custom_headers: dict[str, str] | None = None,
    timeout_seconds: int = 30,
) -> DeliveryResult:
    """
    Make a single synchronous HTTP POST delivery attempt.

    Standard headers sent:
      Content-Type: application/json
      X-Lesovik-Event: <event_type>
      X-Lesovik-Delivery: <delivery_id>
      X-Lesovik-Timestamp: <unix_ts>
      X-Lesovik-Signature: sha256=<hmac>

    A 2xx response is considered success.
    """
    try:
        assert_url_is_safe(target_url)
    except UnsafeUrlError as exc:
        return DeliveryResult(success=False, error=f"Blocked: {exc}")

    body = json.dumps(payload, default=str).encode()
    timestamp = str(int(time.time()))

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "X-Lesovik-Event": event_type,
        "X-Lesovik-Delivery": delivery_id,
        "X-Lesovik-Timestamp": timestamp,
        "X-Lesovik-Signature": compute_signature(secret, body),
    }
    if custom_headers:
        headers.update(custom_headers)

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            resp = client.post(target_url, content=body, headers=headers)
        success = resp.is_success
        return DeliveryResult(
            success=success,
            status_code=resp.status_code,
            response_body=resp.text[:4096],
        )
    except httpx.TimeoutException as exc:
        return DeliveryResult(success=False, error=f"Timeout: {exc}")
    except httpx.RequestError as exc:
        return DeliveryResult(success=False, error=f"RequestError: {exc}")


def send_webhook(
    *,
    url: str,
    method: str,
    payload: dict[str, Any],
    timeout_seconds: int = 15,
) -> DeliveryResult:
    """
    Fire a single ad-hoc webhook call for a rule's `call_webhook` action.

    Unlike `deliver()` there is no subscriber secret to sign with (the URL
    and payload come straight from the rule definition), but the same SSRF
    guard and redirect policy apply.
    """
    try:
        assert_url_is_safe(url)
    except UnsafeUrlError as exc:
        return DeliveryResult(success=False, error=f"Blocked: {exc}")

    method = method.upper() if method else "POST"
    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        return DeliveryResult(success=False, error=f"Unsupported method {method!r}")

    headers = {"Content-Type": "application/json", "X-Lesovik-Timestamp": str(int(time.time()))}
    body = None if method == "GET" else json.dumps(payload, default=str).encode()

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            resp = client.request(method, url, content=body, headers=headers)
        return DeliveryResult(
            success=resp.is_success,
            status_code=resp.status_code,
            response_body=resp.text[:4096],
        )
    except httpx.TimeoutException as exc:
        return DeliveryResult(success=False, error=f"Timeout: {exc}")
    except httpx.RequestError as exc:
        return DeliveryResult(success=False, error=f"RequestError: {exc}")
