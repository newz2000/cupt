"""Contract tests for non-interactive CLI behavior."""

from unittest.mock import patch

from cupt.errors import EXIT_INVALID_INPUT
from cupt.main import cli


def test_no_interactive_disables_active_output(runner):
    result = runner.invoke(cli, ["--no-interactive", "active"])
    assert result.exit_code == 0
    assert result.output == ""


def test_work_requires_json_or_interactive(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [
        {"id": "t1", "name": "Task", "status": {"type": "open"}}
    ]
    with patch(
        "cupt.work.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(cli, ["--no-interactive", "work"])
    assert result.exit_code == EXIT_INVALID_INPUT
    assert "interactive-only" in result.output


def test_auth_failure_uses_documented_exit_code(runner):
    with patch("cupt.context.ConfigManager") as mock_config:
        mock_config.return_value.is_authenticated.return_value = False
        result = runner.invoke(cli, ["list", "--json"])
    assert result.exit_code == 2
    assert "Not authenticated" in result.output
