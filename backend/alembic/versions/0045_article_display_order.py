"""Add support.article.display_order — admin-controlled ordering for
Knowledge Base articles (used by the Learning page's materials and steps).

Revision ID: 0045
Revises: 0044
Create Date: 2026-10-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "article",
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        schema="support",
    )


def downgrade() -> None:
    op.drop_column("article", "display_order", schema="support")
