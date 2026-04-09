from unittest.mock import MagicMock, patch

import pytest

from cupt.time_tracker import time_group

_MODULE = "cupt.time_tracker.get_client_context"


def _ctx(mock_config, mock_client, team_id="team1"):
    return (mock_config, mock_client, team_id)


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_time_start_success(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = None
        result = runner.invoke(time_group, ["start", "task1"])
        assert result.exit_code == 0
        assert "Started tracking" in result.output
        mock_client.start_timer.assert_called_once_with("team1", "task1")


def test_time_start_already_running(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = {"id": "timer1"}
        result = runner.invoke(time_group, ["start", "task1"])
        assert "already running" in result.output
        mock_client.start_timer.assert_not_called()


def test_start_timer_no_team_id(runner):
    with patch(_MODULE, return_value=(None, None, None)):
        result = runner.invoke(time_group, ["start", "task1"])
        assert result.exit_code == 0


def test_time_auth_error(runner):
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        result = runner.invoke(time_group, ["start", "task1"])
        assert "Not authenticated" in result.output


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def test_time_stop_success(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = {"id": "timer1"}
        result = runner.invoke(time_group, ["stop"])
        assert "Timer stopped" in result.output
        mock_client.stop_timer.assert_called_once()


def test_time_stop_with_task_id(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = {"id": "timer1"}
        result = runner.invoke(time_group, ["stop", "task1"])
        assert result.exit_code == 0
        assert "Timer stopped" in result.output


def test_stop_timer_no_team_id(runner):
    with patch(_MODULE, return_value=(None, None, None)):
        result = runner.invoke(time_group, ["stop"])
        assert result.exit_code == 0


def test_stop_timer_not_running(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = None
        result = runner.invoke(time_group, ["stop"])
        assert "No timer is currently running" in result.output


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_time_status_running(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = {
            "task_id": "abc",
            "start": 1_600_000_000_000,
        }
        result = runner.invoke(time_group, ["status"])
        assert "Timer is running" in result.output
        assert "abc" in result.output


def test_timer_status_no_team_id(runner):
    with patch(_MODULE, return_value=(None, None, None)):
        result = runner.invoke(time_group, ["status"])
        assert result.exit_code == 0


def test_timer_status_no_timer(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        mock_client.get_running_timer.return_value = None
        result = runner.invoke(time_group, ["status"])
        assert "No timer is currently running" in result.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_time_add_success(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        result = runner.invoke(time_group, ["add", "task1", "1h", "-m", "work"])
        assert result.exit_code == 0
        assert "Added 1h to task task1" in result.output
        mock_client.add_time_entry.assert_called_once()


def test_add_time_no_team_id(runner):
    with patch(_MODULE, return_value=(None, None, None)):
        result = runner.invoke(time_group, ["add", "task1", "1h"])
        assert result.exit_code == 0


def test_add_time_invalid_duration(runner, mock_config, mock_client):
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        result = runner.invoke(time_group, ["add", "task1", "xyz"])
        assert "Invalid duration format" in result.output
