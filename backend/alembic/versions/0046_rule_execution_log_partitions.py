"""logic.rule_execution_log: backfill missing monthly partitions.

0004_logic_rules only ever created partitions through 2026-06 ("Initial
partitions — 3 months (add more via scheduled job)") — no such job was
ever actually added anywhere in the codebase, so every rule execution
from July 2026 onward has been failing to log with a PostgreSQL
CHECK-violation ("no partition of relation ... found for row"), silently
(RuleExecutionLog writes are deliberately best-effort/non-fatal — the
rule itself still runs correctly, only its audit trail was missing).
Found via manual QA against production while verifying ТЗ item 13.

Creates partitions through the end of 2028 — a deliberately large buffer
so this doesn't quietly recur in another few months. A new Celery beat
task (ensure_rule_execution_log_partitions, see
app/worker/tasks/partitions.py) now also runs monthly and extends the
partition range on its own going forward.

Revision ID: 0046
Revises: 0045
Create Date: 2026-10-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONTHS = (
    [(2026, m) for m in range(7, 13)]
    + [(2027, m) for m in range(1, 13)]
    + [(2028, m) for m in range(1, 13)]
)


def upgrade() -> None:
    for year, month in _MONTHS:
        next_year = year + (1 if month == 12 else 0)
        next_month = 1 if month == 12 else month + 1
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS logic.rule_execution_log_{year}_{month:02d}
            PARTITION OF logic.rule_execution_log
            FOR VALUES FROM ('{year}-{month:02d}-01') TO ('{next_year}-{next_month:02d}-01')
        """)


def downgrade() -> None:
    # Backfilled partitions are purely additive storage for future months —
    # leaving them in place on downgrade is safe and avoids destroying any
    # rows a forward-migrated system may have already written into them.
    pass
