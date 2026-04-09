from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cupt.main import cli


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.3.0" in result.output


def test_config_show():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        instance = mock_config.return_value
        instance.get.side_effect = lambda key, default=None: "test-value"
        instance.is_authenticated.return_value = True

        result = runner.invoke(cli, ["config", "--show"])
        assert result.exit_code == 0
        assert "Team ID: test-value" in result.output


def test_config_set():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config:
        instance = mock_config.return_value
        result = runner.invoke(cli, ["config", "--team-id", "123"])
        assert result.exit_code == 0
        instance.set.assert_called_with("user.team_id", "123")


def test_status_authenticated():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ) as mock_client:

        mock_config.return_value.is_authenticated.return_value = True
        mock_client.return_value.get_user.return_value = {"user": {"username": "matt"}}
        mock_client.return_value.get_teams.return_value = []

        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Authenticated as: matt" in result.output


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


def test_status_with_team_found():
    runner = CliRunner()
    with patch("cupt.main.ConfigManager") as mock_config, patch(
        "cupt.main.ClickUpClient"
    ) as mock_client:
        mock_config.return_value.is_authenticated.return_value = True
        mock_config.return_value.get.side_effect = lambda key, default=None: {
            "auth.access_token": "token",
            "user.team_id": "team1",
        }.get(key, default)
        mock_client.return_value.get_user.return_value = {"user": {"username": "matt"}}
        mock_client.return_value.get_teams.return_value = [
            {"id": "team1", "name": "My Team"}
        ]
        result = runner.invoke(cli, ["status"])
        assert "My Team" in result.output


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
    ) as mock_client:

        instance = mock_config.return_value
        instance.get.return_value = None  # No existing token

        # Choice 2 (Personal Token), then the token itself
        result = runner.invoke(cli, ["auth"], input="2\npk_12345\n")

        assert result.exit_code == 0
        assert "Authenticated with Personal API Token" in result.output
        instance.set.assert_any_call("auth.access_token", "pk_12345")
