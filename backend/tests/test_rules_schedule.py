"""
Schedule-triggered rules (ТЗ 3.5.1 "Расчёт"/"Уведомление": работа по
расписанию, а не только по событию).

Unit:
  - RuleTrigger validates schedule_kind/cron/relative_date shape
  - cron field/tick matching in the periodic sweep task
  - date parsing for relative_date candidates
"""

from datetime import UTC, datetime

import pytest
from app.schemas.rules import RuleTrigger
from app.worker.tasks.rules_schedule import _cron_matches_now, _parse_date


class TestRuleTriggerScheduleValidation:
    def test_cron_trigger_is_valid(self) -> None:
        t = RuleTrigger(
            event="schedule",
            schedule_kind="cron",
            cron={"minute": "0", "hour": "0", "day_of_month": "1"},
        )
        assert t.cron is not None
        assert t.cron.day_of_month == "1"

    def test_relative_date_trigger_is_valid(self) -> None:
        t = RuleTrigger(
            event="schedule",
            schedule_kind="relative_date",
            relative_date={"date_field": "due_date", "offset_days": -3},
        )
        assert t.relative_date is not None
        assert t.relative_date.offset_days == -3

    def test_schedule_without_kind_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuleTrigger(event="schedule")

    def test_cron_kind_without_cron_body_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuleTrigger(event="schedule", schedule_kind="cron")

    def test_relative_date_kind_without_body_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuleTrigger(event="schedule", schedule_kind="relative_date")

    def test_cron_on_non_schedule_event_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuleTrigger(event="record.created", cron={"minute": "0"})

    def test_relative_date_on_non_schedule_event_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            RuleTrigger(
                event="record.updated",
                relative_date={"date_field": "due_date", "offset_days": -3},
            )

    def test_non_schedule_events_still_work_unchanged(self) -> None:
        t = RuleTrigger(event="field.changed", watch_fields=["status"])
        assert t.schedule_kind is None
        assert t.cron is None


class TestCronMatchesNow:
    def test_wildcard_matches_any_tick(self) -> None:
        cron = {
            "minute": "0",
            "hour": "*",
            "day_of_month": "*",
            "month_of_year": "*",
            "day_of_week": "*",
        }
        assert _cron_matches_now(cron, datetime(2026, 3, 17, 5, 0, tzinfo=UTC))
        assert _cron_matches_now(cron, datetime(2026, 3, 17, 23, 0, tzinfo=UTC))

    def test_monthly_first_only_matches_first_of_month(self) -> None:
        cron = {
            "minute": "0",
            "hour": "0",
            "day_of_month": "1",
            "month_of_year": "*",
            "day_of_week": "*",
        }
        assert _cron_matches_now(cron, datetime(2026, 3, 1, 0, 0, tzinfo=UTC))
        assert not _cron_matches_now(cron, datetime(2026, 3, 2, 0, 0, tzinfo=UTC))

    def test_hour_mismatch_does_not_match(self) -> None:
        cron = {
            "minute": "0",
            "hour": "9",
            "day_of_month": "*",
            "month_of_year": "*",
            "day_of_week": "*",
        }
        assert not _cron_matches_now(cron, datetime(2026, 3, 1, 10, 0, tzinfo=UTC))

    def test_comma_separated_hours(self) -> None:
        cron = {
            "minute": "0",
            "hour": "9,18",
            "day_of_month": "*",
            "month_of_year": "*",
            "day_of_week": "*",
        }
        assert _cron_matches_now(cron, datetime(2026, 3, 1, 9, 0, tzinfo=UTC))
        assert _cron_matches_now(cron, datetime(2026, 3, 1, 18, 0, tzinfo=UTC))
        assert not _cron_matches_now(cron, datetime(2026, 3, 1, 12, 0, tzinfo=UTC))

    def test_malformed_field_never_matches(self) -> None:
        cron = {
            "minute": "0",
            "hour": "not-a-number",
            "day_of_month": "*",
            "month_of_year": "*",
            "day_of_week": "*",
        }
        assert not _cron_matches_now(cron, datetime(2026, 3, 1, 0, 0, tzinfo=UTC))


class TestParseDate:
    def test_parses_iso_date(self) -> None:
        assert _parse_date("2026-03-17") is not None

    def test_parses_iso_datetime(self) -> None:
        assert _parse_date("2026-03-17T14:30:00") is not None

    def test_rejects_garbage(self) -> None:
        assert _parse_date("not-a-date") is None

    def test_rejects_none(self) -> None:
        assert _parse_date(None) is None

    def test_rejects_non_string(self) -> None:
        assert _parse_date(12345) is None
