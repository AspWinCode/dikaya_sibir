"""Add catalog.app_invite_link — shareable invite links for apps

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_invite_link",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "app_id",
            UUID(as_uuid=True),
            sa.ForeignKey("catalog.app.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("allow_signup", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="catalog",
    )
    op.create_index(
        "ix_app_invite_link_app_id", "app_invite_link", ["app_id"], schema="catalog"
    )


def downgrade() -> None:
    op.drop_index("ix_app_invite_link_app_id", table_name="app_invite_link", schema="catalog")
    op.drop_table("app_invite_link", schema="catalog")
