import pytest

from cupt.utils import (
    format_date,
    format_duration,
    format_task_status,
    get_terminal_width,
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


def test_format_task_status():
    assert "⟳" in format_task_status("in progress")
    assert "✓" in format_task_status("complete")
    assert "○" in format_task_status("to do")
    assert "?" == format_task_status("unknown")
