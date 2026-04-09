"""Tests for cupt/summary.py — daily summary command."""

import time
from unittest.mock import MagicMock, patch

import pytest

from cupt.summary import summary_cmd
from cupt.utils import format_duration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(mock_config, mock_client, team_id="team1"):
    return (mock_config, mock_client, team_id)


def _open_task(task_id, name):
    return {"id": task_id, "name": name, "status": {"status": "open", "type": "open"}}


def _closed_task(task_id, name):
    return {
        "id": task_id,
        "name": name,
        "status": {"status": "done", "type": "closed"},
    }


def _empty_client(mock_client):
    """Configure mock_client to return empty data for all summary endpoints."""
    mock_client.get_team_tasks.return_value = []
    mock_client.get_time_entries.return_value = []
    mock_client.get_running_timer.return_value = None


# ---------------------------------------------------------------------------
# Basic rendering
# ---------------------------------------------------------------------------


def test_summary_cmd_empty(runner, mock_config, mock_client):
    """With no data, all sections show empty-state messages."""
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        _empty_client(mock_client)
        result = runner.invoke(summary_cmd)

        assert result.exit_code == 0
        assert "YOUR SUMMARY" in result.output
        assert "Nothing due today" in result.output
        assert "Nothing overdue" in result.output
        assert "Nothing completed today" in result.output
        assert "0m" in result.output
        assert "Running: none" in result.output


def test_summary_cmd_all_flag(runner, mock_config, mock_client):
    """--all renders TEAM SUMMARY instead of YOUR SUMMARY."""
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        _empty_client(mock_client)
        result = runner.invoke(summary_cmd, ["--all"])

        assert result.exit_code == 0
        assert "TEAM SUMMARY" in result.output


# ---------------------------------------------------------------------------
# Due today
# ---------------------------------------------------------------------------


def test_summary_due_today_shows_tasks(runner, mock_config, mock_client):
    """Tasks returned for the due-today fetch appear in the DUE TODAY section."""
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [_open_task("t1", "Fix bug")]
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert "Fix bug" in result.output
        assert "DUE TODAY" in result.output


def test_summary_due_today_task_count(runner, mock_config, mock_client):
    """Section header shows the correct task count."""
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            _open_task("t1", "Task A"),
            _open_task("t2", "Task B"),
        ]
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert "2 tasks" in result.output


# ---------------------------------------------------------------------------
# Overdue
# ---------------------------------------------------------------------------


def test_summary_overdue_shows_tasks(runner, mock_config, mock_client):
    """Overdue tasks appear in the OVERDUE section with a due date column."""
    overdue_task = {
        "id": "t1",
        "name": "Old task",
        "status": {"status": "open", "type": "open"},
        "due_date": "1609459200000",  # 2021-01-01
    }
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [overdue_task]
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert "Old task" in result.output
        assert "OVERDUE" in result.output


# ---------------------------------------------------------------------------
# Completed today
# ---------------------------------------------------------------------------


def test_summary_completed_today(runner, mock_config, mock_client):
    """Closed tasks from get_team_tasks appear in COMPLETED TODAY."""

    def _get_team_tasks(team_id, params=None):
        params = params or {}
        # _fetch_completed_today passes include_closed="true"
        if params.get("include_closed"):
            return [_closed_task("t2", "Finished feature")]
        return []

    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.side_effect = _get_team_tasks
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert "Finished feature" in result.output
        assert "COMPLETED TODAY" in result.output


def test_summary_open_tasks_excluded_from_completed(runner, mock_config, mock_client):
    """Open tasks returned by the completed fetch are not shown in COMPLETED TODAY."""

    def _get_team_tasks(team_id, params=None):
        params = params or {}
        if params.get("include_closed"):
            # Returns an open task — should be filtered out
            return [_open_task("t1", "Still open")]
        return []

    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.side_effect = _get_team_tasks
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert "Nothing completed today" in result.output


# ---------------------------------------------------------------------------
# Time tracking
# ---------------------------------------------------------------------------


def test_summary_time_entries_summed(runner, mock_config, mock_client):
    """Time entry durations are summed and formatted correctly."""
    # 1 hour + 30 minutes = 5400000 ms
    entries = [{"duration": "3600000"}, {"duration": "1800000"}]
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = []
        mock_client.get_time_entries.return_value = entries
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert format_duration(5400000) in result.output


def test_summary_running_timer_shown(runner, mock_config, mock_client):
    """A running timer shows the task name and elapsed time."""
    start_ms = int(time.time() * 1000) - 300_000  # started 5 minutes ago
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = []
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = {
            "start": str(start_ms),
            "task": {"name": "Deep work session"},
        }

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert "Deep work session" in result.output
        assert "Running:" in result.output


def test_summary_time_entries_error_degrades_gracefully(
    runner, mock_config, mock_client
):
    """A failure in the time-entries fetch doesn't crash the summary."""
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = []
        mock_client.get_time_entries.side_effect = Exception("permission denied")
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        # Time section should still render with 0m
        assert "0m" in result.output


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_summary_api_error(runner, mock_config, mock_client):
    """A fatal fetch error prints an error message."""
    with patch(
        "cupt.summary.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.side_effect = Exception("Network error")
        mock_client.get_time_entries.return_value = []
        mock_client.get_running_timer.return_value = None

        result = runner.invoke(summary_cmd)
        assert result.exit_code == 0
        assert "Failed to fetch summary data" in result.output


def test_summary_auth_error(runner):
    """Unauthenticated users see the standard auth error."""
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        result = runner.invoke(summary_cmd)
        assert "Not authenticated" in result.output
