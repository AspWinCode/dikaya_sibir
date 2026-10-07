import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FieldPermission(Base):
    """
    Field-level ABAC row.

    Semantics: open by default, explicit deny.
    - No row for (entity_id, field_name, role_id) → ALLOW
    - Row with can_read=False → that role CANNOT read this field
    - Row with can_write=False → that role CANNOT write this field
    - User holds multiple roles → DENY from ANY role wins
    """

    __tablename__ = "field_permission"
    __table_args__ = (
        sa.UniqueConstraint("entity_id", "field_name", "role_id", name="uq_field_permission"),
        {"schema": "security"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    app_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    role_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    can_read: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="true")
    can_write: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
