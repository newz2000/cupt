import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cupt import __version__
from cupt.errors import EXIT_AUTH
from cupt.main import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_config_show():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        instance = mock_config.return_value
        instance.get.side_effect = lambda key, default=None: "test-value"
        instance.is_authenticated.return_value = True

        result = runner.invoke(cli, ["config", "--show"])
        assert result.exit_code == 0
        assert "Workspace ID: test-value" in result.output


def test_config_set():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        instance = mock_config.return_value
        result = runner.invoke(cli, ["config", "--workspace-id", "123"])
        assert result.exit_code == 0
        instance.set.assert_called_with("user.workspace_id", "123")


def test_status_authenticated():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ) as mock_client:
        mock_config.return_value.is_authenticated.return_value = True
        mock_client.return_value.get_user.return_value = {"user": {"username": "matt"}}
        mock_client.return_value.get_workspaces.return_value = []

        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Authenticated as: matt" in result.output


def test_teams_lists_user_groups():
    runner = CliRunner()
    config, client = MagicMock(), MagicMock()
    with patch(
        "cupt.main.get_client_context", return_value=(config, client, "workspace1")
    ):
        client.get_teams.return_value = [
            {"id": "g1", "name": "MattTech", "members": [{"id": "u1"}, {"id": "u2"}]},
            {"id": "g2", "name": "AI Agent", "members": []},
        ]
        result = runner.invoke(cli, ["teams"])
        assert result.exit_code == 0
        assert "MattTech" in result.output
        assert "AI Agent" in result.output
        assert "g1" in result.output
        # Workspace id was resolved from config, not the CLI.
        client.get_teams.assert_called_once_with("workspace1")


def test_teams_not_authenticated():
    """`cupt teams` used to warn and exit 0, unlike every other command."""
    runner = CliRunner()
    with patch("cupt.context.ConfigManager") as mock_config:
        mock_config.return_value.is_authenticated.return_value = False
        result = runner.invoke(cli, ["teams"])
        assert result.exit_code == EXIT_AUTH
        assert "Not authenticated" in result.output


def test_logout():
    runner = CliRunner()
    with patch("cupt.main.OAuthManager") as mock_oauth:
        result = runner.invoke(cli, ["logout"])
        assert result.exit_code == 0
        mock_oauth.return_value.logout.assert_called_once()


def test_status_not_authenticated():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        mock_config.return_value.is_authenticated.return_value = False
        result = runner.invoke(cli, ["status"])
        assert "Not authenticated" in result.output


def test_status_with_workspace_found():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ) as mock_client:
        mock_config.return_value.is_authenticated.return_value = True
        mock_config.return_value.get.side_effect = lambda key, default=None: {
            "auth.access_token": "token",
            "user.workspace_id": "ws1",
        }.get(key, default)
        mock_client.return_value.get_user.return_value = {"user": {"username": "matt"}}
        mock_client.return_value.get_workspaces.return_value = [
            {"id": "ws1", "name": "My Workspace"}
        ]
        result = runner.invoke(cli, ["status"])
        assert "My Workspace" in result.output


def test_status_exception():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ) as mock_client:
        mock_config.return_value.is_authenticated.return_value = True
        mock_client.return_value.get_user.side_effect = Exception("API Error")
        result = runner.invoke(cli, ["status"])
        assert "Failed to get status" in result.output


def test_config_clear_cache():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        result = runner.invoke(cli, ["config", "--clear-cache"])
        assert result.exit_code == 0
        mock_config.return_value.clear_cache.assert_called_once()


def test_config_set_api_token():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        result = runner.invoke(cli, ["config", "--api-token", "pk_abc"])
        assert result.exit_code == 0
        mock_config.return_value.set.assert_any_call("auth.access_token", "pk_abc")


def test_config_no_options_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["config"])
    assert result.exit_code == 0


def test_auth_already_authenticated():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        mock_config.return_value.get.return_value = "pk_existing_token"
        result = runner.invoke(cli, ["auth"])
        assert "Already authenticated" in result.output


def test_auth_invalid_token_format():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        mock_config.return_value.get.return_value = None
        result = runner.invoke(cli, ["auth"], input="2\nnot_a_pk_token\n")
        assert "should start with 'pk_'" in result.output


def test_auth_personal_token_success():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ):
        instance = mock_config.return_value
        instance.get.return_value = None  # No existing token

        # Choice 2 (Personal Token), then the token itself
        result = runner.invoke(cli, ["auth"], input="2\npk_12345\n")

        assert result.exit_code == 0
        assert "Authenticated with Personal API Token" in result.output
        instance.set.assert_any_call("auth.access_token", "pk_12345")


# ---------------------------------------------------------------------------
# `cupt status --json` — machine-readable identity
# ---------------------------------------------------------------------------


def _status_json(runner, monkeypatch=None):
    """Invoke `status --json` against a fully mocked client, return the payload."""
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ) as mock_client:
        mock_config.return_value.is_authenticated.return_value = True
        mock_config.return_value.get.side_effect = lambda key, default=None: {
            "auth.access_token": "token",
            "user.workspace_id": "ws1",
            "user.user_id": "14740268",
            "user.username": "matt",
        }.get(key, default)
        mock_client.return_value.get_user.return_value = {
            "user": {"id": 14740268, "username": "matt", "email": "matt@example.com"}
        }
        mock_client.return_value.get_workspaces.return_value = [
            {"id": "ws1", "name": "My Workspace"}
        ]
        result = runner.invoke(cli, ["status", "--json"])
    return result


def test_status_json_carries_user_id_not_just_a_name():
    """Names are not identifiers — a workspace can hold several accounts for
    one human or bot, so a script needs the id."""
    result = _status_json(CliRunner())
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["user"]["id"] == 14740268
    assert payload["user"]["username"] == "matt"
    assert payload["user"]["email"] == "matt@example.com"
    assert payload["workspace"] == {"id": "ws1", "name": "My Workspace"}


def test_status_json_reports_the_config_home_actually_loaded(tmp_path, monkeypatch):
    """A caller must be able to confirm which profile it is acting out of."""
    monkeypatch.setenv("CUPT_HOME", str(tmp_path / "agent"))
    result = _status_json(CliRunner())
    payload = json.loads(result.stdout)
    assert payload["config_home"] == str(tmp_path / "agent")
    assert payload["version"] == __version__


def test_status_json_prints_only_json_to_stdout():
    """stdout is data: no success banner may contaminate the JSON."""
    result = _status_json(CliRunner())
    json.loads(result.stdout)  # raises if anything else was written


def test_status_unauthenticated_exits_non_zero():
    """Signed out is a failure, not an empty success — a script that reads it
    as 'no data' would go on to act as nobody at all."""
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        mock_config.return_value.is_authenticated.return_value = False
        result = runner.invoke(cli, ["status", "--json"])
        assert result.exit_code == EXIT_AUTH
        assert result.stdout == ""
