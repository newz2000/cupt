import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from cupt.main import cli

def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert "0.1.0" in result.output

def test_config_show():
    runner = CliRunner()
    with patch('cupt.main.ConfigManager') as mock_config:
        instance = mock_config.return_value
        instance.get.side_effect = lambda key, default=None: "test-value"
        instance.is_authenticated.return_value = True
        
        result = runner.invoke(cli, ['config', '--show'])
        assert result.exit_code == 0
        assert "Team ID: test-value" in result.output

def test_config_set():
    runner = CliRunner()
    with patch('cupt.main.ConfigManager') as mock_config:
        instance = mock_config.return_value
        result = runner.invoke(cli, ['config', '--team-id', '123'])
        assert result.exit_code == 0
        instance.set.assert_called_with('user.team_id', '123')

def test_status_authenticated():
    runner = CliRunner()
    with patch('cupt.main.ConfigManager') as mock_config, \
         patch('cupt.main.ClickUpClient') as mock_client:
        
        mock_config.return_value.is_authenticated.return_value = True
        mock_client.return_value.get_user.return_value = {"user": {"username": "matt"}}
        mock_client.return_value.get_teams.return_value = []
        
        result = runner.invoke(cli, ['status'])
        assert result.exit_code == 0
        assert "Authenticated as: matt" in result.output

def test_logout():
    runner = CliRunner()
    with patch('cupt.main.OAuthManager') as mock_oauth:
        result = runner.invoke(cli, ['logout'])
        assert result.exit_code == 0
        mock_oauth.return_value.logout.assert_called_once()

def test_auth_personal_token_success():
    runner = CliRunner()
    with patch('cupt.main.ConfigManager') as mock_config, \
         patch('cupt.main.ClickUpClient') as mock_client:
        
        instance = mock_config.return_value
        instance.get.return_value = None # No existing token
        
        # Choice 2 (Personal Token), then the token itself
        result = runner.invoke(cli, ['auth'], input="2\npk_12345\n")
        
        assert result.exit_code == 0
        assert "Authenticated with Personal API Token" in result.output
        instance.set.assert_any_call('auth.access_token', 'pk_12345')
