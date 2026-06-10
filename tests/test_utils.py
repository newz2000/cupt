from datetime import datetime, timedelta

import pytest

from cupt.utils import (
    format_date,
    format_duration,
    format_task_status,
    get_terminal_width,
    parse_due_date,
    parse_duration,
    truncate_text,
)


def test_truncate_text():
    assert truncate_text("Hello World", 5) == "He..."
    assert truncate_text("Short", 10) == "Short"
    assert truncate_text(None, 5) == ""
    assert truncate_text("Exactly5", 8) == "Exactly5"


def test_truncate_text_none_means_no_truncation():
    long = "x" * 500
    assert truncate_text(long, None) == long


class _FakeStream:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_get_terminal_width_none_when_not_tty():
    assert get_terminal_width(_FakeStream(False)) is None


def test_get_terminal_width_respects_columns_env(monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.setenv("LINES", "50")
    assert get_terminal_width(_FakeStream(True)) == 200


def test_parse_duration():
    assert parse_duration("30m") == 30 * 60 * 1000
    assert parse_duration("1h") == 60 * 60 * 1000
    assert parse_duration("1h30m") == 90 * 60 * 1000
    assert parse_duration("  2h  ") == 120 * 60 * 1000
    assert parse_duration("invalid") is None
    assert parse_duration(None) is None
    assert parse_duration(123) is None


def test_format_duration():
    assert format_duration(30 * 60 * 1000) == "30m"
    assert format_duration(60 * 60 * 1000) == "1h"
    assert format_duration(90 * 60 * 1000) == "1h30m"
    assert format_duration(0) == "0m"
    assert format_duration(None) == "0m"


def test_format_date():
    # 1767088800000 is Dec 30, 2025
    assert "2025-12-30" in format_date(1767088800000)
    assert "2025-12-30" in format_date("1767088800000")  # String ts
    assert format_date(None) == "No date"
    assert format_date("not a ts") == "Invalid date"


def test_parse_due_date_none_and_empty():
    assert parse_due_date(None) is None
    assert parse_due_date("") is None


def test_parse_due_date_today_and_tomorrow():
    today = parse_due_date("today")
    tomorrow = parse_due_date("tomorrow")
    assert isinstance(today, int) and today > 0
    # Tomorrow is roughly 24h later (allow a few seconds of clock skew).
    assert 23 * 60 * 60 * 1000 < tomorrow - today < 25 * 60 * 60 * 1000


def test_parse_due_date_relative():
    soon = parse_due_date("+2d")
    week = parse_due_date("+1w")
    hour = parse_due_date("+3h")
    assert all(isinstance(x, int) and x > 0 for x in (soon, week, hour))
    assert week > soon > hour


def test_parse_due_date_iso_formats():
    assert parse_due_date("2026-12-31") > 0
    assert parse_due_date("2026-12-31 14:30") > 0
    # Whitespace tolerated.
    assert parse_due_date("  2026-12-31  ") > 0


def test_parse_due_date_epoch_passthrough():
    """Raw epoch ms (used by agent callers like Hermes) passes straight
    through so tool integrations don't need to format dates."""
    assert parse_due_date("1767088800000") == 1767088800000


def test_parse_due_date_invalid_raises():
    with pytest.raises(ValueError, match="Could not parse"):
        parse_due_date("nope")


def test_format_task_status():
    assert "⟳" in format_task_status("in progress")
    assert "✓" in format_task_status("complete")
    assert "○" in format_task_status("to do")
    assert "?" == format_task_status("unknown")
