"""
Field-level AES-256-GCM encryption for sensitive record fields (ТЗ 3.13:
"Шифрование данных в хранилище: AES-256").

Only fields explicitly flagged `Field.is_sensitive` are encrypted — this is
NOT full-disk/tablespace encryption (that's an infrastructure concern: an
encrypted volume under Postgres's data directory, outside application code).
Encrypted values live in the record's JSONB payload as an opaque token and
can't be filtered, sorted, or searched — callers choosing which fields to
mark sensitive are accepting that trade-off.

Boundary: encryption/decryption happens ONLY inside RecordService, at the
point payloads cross into/out of the `data.record` table. Every other
consumer that gets a payload through RecordService's public methods
(RuleService, exports, the API layer) already sees plaintext. Code that
reads/writes app.models.data.Record directly (app/worker/tasks/sandbox.py's
rule-mutation persistence, app/services/imports.py) bypasses this and is a
known, separate gap — see ТЗ audit notes.
"""

import base64
import json
import os
from typing import Any, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_TOKEN_PREFIX = "enc:v1:"  # noqa: S105 — a format-version marker string, not a secret


class FieldCryptoError(Exception):
    pass


def _key() -> bytes:
    try:
        key = base64.b64decode(settings.FIELD_ENCRYPTION_KEY, validate=True)
    except Exception as exc:
        raise FieldCryptoError("FIELD_ENCRYPTION_KEY is not valid base64") from exc
    if len(key) != 32:
        raise FieldCryptoError(
            f"FIELD_ENCRYPTION_KEY must decode to 32 bytes for AES-256, got {len(key)}"
        )
    return key


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_TOKEN_PREFIX)


def encrypt_value(value: Any) -> str:
    """Encrypt any JSON-serializable value into an opaque token string.
    A fresh random nonce is generated per call (AES-GCM requires a unique
    nonce per encryption under the same key)."""
    if is_encrypted(value):
        return cast(str, value)  # is_encrypted() already confirmed this is a str
    plaintext = json.dumps(value, ensure_ascii=False).encode("utf-8")
    nonce = os.urandom(
        12
    )  # AES-GCM standard nonce size; must be unique per encryption under this key
    ciphertext = AESGCM(_key()).encrypt(nonce, plaintext, None)
    return _TOKEN_PREFIX + base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_value(token: str) -> Any:
    """Reverse of encrypt_value. Raises FieldCryptoError on tampered
    ciphertext or a key mismatch (e.g. FIELD_ENCRYPTION_KEY rotated without
    re-encrypting existing data)."""
    if not is_encrypted(token):
        return token
    raw = base64.b64decode(token[len(_TOKEN_PREFIX) :])
    nonce, ciphertext = raw[:12], raw[12:]
    try:
        plaintext = AESGCM(_key()).decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise FieldCryptoError(
            "Failed to decrypt field value (wrong key or corrupted data)"
        ) from exc
    return json.loads(plaintext.decode("utf-8"))


def encrypt_sensitive_fields(
    payload: dict[str, Any], sensitive_field_names: set[str]
) -> dict[str, Any]:
    if not sensitive_field_names:
        return payload
    result = dict(payload)
    for name in sensitive_field_names:
        if name in result and result[name] is not None:
            result[name] = encrypt_value(result[name])
    return result


def decrypt_sensitive_fields(
    payload: dict[str, Any], sensitive_field_names: set[str]
) -> dict[str, Any]:
    if not sensitive_field_names:
        return payload
    result = dict(payload)
    for name in sensitive_field_names:
        v = result.get(name)
        if is_encrypted(v):
            try:
                result[name] = decrypt_value(cast(str, v))
            except FieldCryptoError:
                result[name] = None  # undecryptable — fail closed, never leak ciphertext as-is
    return result


def mask_value(value: Any) -> str:
    """Redacted preview for a sensitive value: keep the last few visible
    characters, blank everything else — the classic "***-**-1234" shape."""
    if value is None:
        return "—"
    s = str(value)
    if len(s) <= 4:
        return "*" * len(s)
    return "*" * (len(s) - 4) + s[-4:]
