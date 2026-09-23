"""Add identity.user.must_change_password — force change of invite temp password

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_column("user", "must_change_password", schema="identity")
