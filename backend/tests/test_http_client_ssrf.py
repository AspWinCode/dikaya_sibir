"""SSRF guard for outbound webhook calls (app.core.http_client).

These are pure-function tests — no DB, no network — verifying that
assert_url_is_safe / deliver / send_webhook refuse private, loopback,
link-local (incl. the 169.254.169.254 cloud metadata address), and
non-http(s) targets before any request is attempted.
"""

import pytest
from app.core.http_client import UnsafeUrlError, assert_url_is_safe, deliver, send_webhook


class TestAssertUrlIsSafe:
    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(UnsafeUrlError, match="scheme"):
            assert_url_is_safe("ftp://example.com/hook")

    def test_rejects_missing_host(self) -> None:
        with pytest.raises(UnsafeUrlError, match="host"):
            assert_url_is_safe("http:///path")

    def test_rejects_loopback(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-public"):
            assert_url_is_safe("http://127.0.0.1/hook")

    def test_rejects_localhost_hostname(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-public"):
            assert_url_is_safe("http://localhost/hook")

    def test_rejects_cloud_metadata_endpoint(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-public"):
            assert_url_is_safe("http://169.254.169.254/latest/meta-data/")

    def test_rejects_private_range_10(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-public"):
            assert_url_is_safe("http://10.0.0.5/hook")

    def test_rejects_private_range_192_168(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-public"):
            assert_url_is_safe("http://192.168.1.1/hook")

    def test_rejects_unspecified(self) -> None:
        with pytest.raises(UnsafeUrlError, match="non-public"):
            assert_url_is_safe("http://0.0.0.0/hook")

    def test_accepts_public_ip(self) -> None:
        assert_url_is_safe("http://8.8.8.8/hook")

    def test_rejects_bad_dns(self) -> None:
        with pytest.raises(UnsafeUrlError, match="DNS resolution"):
            assert_url_is_safe("http://this-domain-should-not-exist-lesovik-test.invalid/hook")


class TestDeliverBlocksUnsafeTargets:
    def test_deliver_blocks_private_target_without_network_call(self) -> None:
        result = deliver(
            target_url="http://127.0.0.1:6379/hook",
            payload={"a": 1},
            event_type="record.created",
            delivery_id="d1",
            secret="s",
        )
        assert result.success is False
        assert result.error is not None
        assert "Blocked" in result.error

    def test_send_webhook_blocks_metadata_endpoint(self) -> None:
        result = send_webhook(
            url="http://169.254.169.254/latest/meta-data/iam/security-credentials/",
            method="GET",
            payload={},
        )
        assert result.success is False
        assert result.error is not None
        assert "Blocked" in result.error

    def test_send_webhook_rejects_unsupported_method(self) -> None:
        result = send_webhook(url="http://8.8.8.8/hook", method="TRACE", payload={})
        assert result.success is False
        assert "Unsupported method" in (result.error or "")
