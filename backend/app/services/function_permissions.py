"""Persistence + lookup of per-role function overrides.

Overrides live in ``identity.resource_permission`` (resource_type="function"),
the same table the resource-permission matrix uses, so no migration is needed.
"""

from __future__ import annotations

import time

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import (
    FUNCTION_ACTION,
    FUNCTION_RESOURCE_TYPE,
    FUNCTIONS_BY_CODE,
    LOCKED_ROLES,
    Overrides,
    overrides_for_desired,
)
from app.models.identity import ResourcePermission

logger = structlog.get_logger(__name__)

# Short in-process cache so gating a request costs no extra query on the hot
# path. Saving a role clears this worker's cache immediately; the other API
# workers pick the change up within _TTL seconds.
_TTL = 5.0
_cache: dict[tuple[str, ...], tuple[float, Overrides]] = {}


def invalidate_cache() -> None:
    _cache.clear()


async def load_overrides(db: AsyncSession, role_ids: list[str] | tuple[str, ...]) -> Overrides:
    """Overrides for the given roles (cached for a few seconds)."""
    roles = tuple(sorted({r for r in role_ids if r not in LOCKED_ROLES}))
    if not roles:
        return {}
    hit = _cache.get(roles)
    now = time.monotonic()
    if hit and now - hit[0] < _TTL:
        return hit[1]
    rows = await db.execute(
        select(ResourcePermission.role_id, ResourcePermission.resource_id, ResourcePermission.allowed).where(
            ResourcePermission.resource_type == FUNCTION_RESOURCE_TYPE,
            ResourcePermission.role_id.in_(roles),
        )
    )
    overrides: Overrides = {(r, code): allowed for r, code, allowed in rows.all()}
    _cache[roles] = (now, overrides)
    return overrides


class UnknownFunctionError(ValueError):
    pass


async def set_role_functions(
    db: AsyncSession, role_id: str, desired: set[str]
) -> Overrides:
    """Make the role's effective functions equal ``desired``; return the rows kept."""
    unknown = sorted(c for c in desired if c not in FUNCTIONS_BY_CODE)
    if unknown:
        raise UnknownFunctionError(f"Unknown functions: {', '.join(unknown)}")

    await db.execute(
        delete(ResourcePermission).where(
            ResourcePermission.role_id == role_id,
            ResourcePermission.resource_type == FUNCTION_RESOURCE_TYPE,
        )
    )
    overrides = overrides_for_desired(role_id, desired)
    for (rid, code), allowed in overrides.items():
        db.add(
            ResourcePermission(
                role_id=rid,
                resource_type=FUNCTION_RESOURCE_TYPE,
                resource_id=code,
                action=FUNCTION_ACTION,
                allowed=allowed,
            )
        )
    await db.flush()
    invalidate_cache()
    logger.info("role_functions_set", role_id=role_id, overrides=len(overrides), allowed=len(desired))
    return overrides

