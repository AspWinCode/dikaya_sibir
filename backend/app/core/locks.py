"""Pessimistic edit locks via Redis.

Lock key:  lock:{resource}:{resource_id}
Lock value: JSON {user_id, acquired_at, holder_name}
TTL: 30 minutes, auto-extended on heartbeat.

Usage:
    async with EditLock(redis, "app", app_id, user_id):
        ...edit...

Or manually:
    lock = EditLock(redis, "entity", entity_id, user_id)
    await lock.acquire()          # raises LockConflictError if taken
    await lock.release()
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

LOCK_TTL = 1800  # 30 minutes
LOCK_PREFIX = "lock"


class LockConflictError(Exception):
    def __init__(self, holder_id: str, holder_name: str) -> None:
        self.holder_id = holder_id
        self.holder_name = holder_name
        super().__init__(f"Resource is locked by {holder_name} ({holder_id})")


class EditLock:
    def __init__(
        self,
        redis: Redis,
        resource: str,
        resource_id: uuid.UUID | str,
        user_id: uuid.UUID,
        holder_name: str = "",
    ) -> None:
        self._redis = redis
        self._key = f"{LOCK_PREFIX}:{resource}:{resource_id}"
        self._user_id = str(user_id)
        self._holder_name = holder_name

    async def acquire(self) -> None:
        value = json.dumps(
            {
                "user_id": self._user_id,
                "holder_name": self._holder_name,
                "acquired_at": datetime.now(UTC).isoformat(),
            }
        )
        # SET NX (only if not exists)
        acquired = await self._redis.set(self._key, value, ex=LOCK_TTL, nx=True)
        if not acquired:
            raw = await self._redis.get(self._key)
            if raw:
                data: dict[str, Any] = json.loads(raw)
                # If same user re-acquires — refresh TTL and allow
                if data["user_id"] == self._user_id:
                    await self._redis.expire(self._key, LOCK_TTL)
                    return
                raise LockConflictError(data["user_id"], data.get("holder_name", ""))

    async def release(self) -> None:
        raw = await self._redis.get(self._key)
        if raw:
            data: dict[str, Any] = json.loads(raw)
            if data["user_id"] == self._user_id:
                await self._redis.delete(self._key)

    async def heartbeat(self) -> None:
        """Extend TTL — call every ~10 min from client-side keep-alive."""
        raw = await self._redis.get(self._key)
        if raw:
            data: dict[str, Any] = json.loads(raw)
            if data["user_id"] == self._user_id:
                await self._redis.expire(self._key, LOCK_TTL)

    async def get_info(self) -> dict[str, Any] | None:
        raw = await self._redis.get(self._key)
        if not raw:
            return None
        return json.loads(raw)  # type: ignore[no-any-return]

    async def __aenter__(self) -> "EditLock":
        await self.acquire()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.release()
