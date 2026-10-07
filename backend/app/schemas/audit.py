"""Audit log schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    actor_email: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    level: str
    ip_address: str | None
    user_agent: str | None
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
