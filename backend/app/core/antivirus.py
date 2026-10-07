"""Async ClamAV client via clamd INSTREAM protocol (TCP)."""

import asyncio
import contextlib
import struct

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_CHUNK_SIZE = 8192
_TIMEOUT = 30.0


class AntivirusError(Exception):
    pass


class ClamAVClient:
    def __init__(self, host: str = "", port: int = 0) -> None:
        self._host = host or settings.CLAMAV_HOST
        self._port = port or settings.CLAMAV_PORT

    async def scan_bytes(self, data: bytes) -> tuple[bool, str]:
        """
        Scan data bytes.
        Returns (is_clean, verdict_string).
        is_clean=True means no virus found.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=_TIMEOUT,
            )
        except (ConnectionRefusedError, OSError) as exc:
            logger.warning("clamav_unreachable", error=str(exc))
            # Fail open in dev — fail closed in prod
            if settings.APP_ENV == "production":
                raise AntivirusError("ClamAV unreachable") from exc
            return True, "SCAN_SKIPPED"

        try:
            # zINSTREAM\0 — null-terminated command
            writer.write(b"zINSTREAM\0")

            # Stream data in chunks: 4-byte big-endian length prefix + chunk
            for i in range(0, len(data), _CHUNK_SIZE):
                chunk = data[i : i + _CHUNK_SIZE]
                writer.write(struct.pack("!I", len(chunk)) + chunk)

            # Zero-length chunk signals end of stream
            writer.write(struct.pack("!I", 0))
            await writer.drain()

            response = (await asyncio.wait_for(reader.read(256), timeout=_TIMEOUT)).decode().strip()
            logger.debug("clamav_response", response=response)

            # Response format: "stream: OK" or "stream: Eicar-Test-Signature FOUND"
            is_clean = response.endswith("OK")
            return is_clean, response
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def ping(self) -> bool:
        """Returns True if ClamAV is reachable."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=5.0,
            )
            writer.write(b"zPING\0")
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(64), timeout=5.0)
            writer.close()
            return b"PONG" in resp
        except Exception:
            return False


def get_antivirus() -> ClamAVClient:
    return ClamAVClient()
