import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from cupt.time_tracker import time_group

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.is_authenticated.return_value = True
    config.get.side_effect = lambda key, default=None: {
        'user.team_id': 'team1',
        'auth.access_token': 'token123'
    }.get(key, default)
    return config

@pytest.fixture
def mock_client():
    return MagicMock()

def test_time_start_success(runner, mock_config, mock_client):
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config), \
         patch('cupt.time_tracker.ClickUpClient', return_value=mock_client):
        
        mock_client.get_running_timer.return_value = None
        result = runner.invoke(time_group, ['start', 'task1'])
        
        assert result.exit_code == 0
        assert "Started tracking" in result.output
        mock_client.start_timer.assert_called_once_with('task1')

def test_time_start_already_running(runner, mock_config, mock_client):
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config), \
         patch('cupt.time_tracker.ClickUpClient', return_value=mock_client):
        
        mock_client.get_running_timer.return_value = {"id": "timer1"}
        result = runner.invoke(time_group, ['start', 'task1'])
        
        assert "already running" in result.output
        mock_client.start_timer.assert_not_called()

def test_time_stop_success(runner, mock_config, mock_client):
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config), \
         patch('cupt.time_tracker.ClickUpClient', return_value=mock_client):
        
        mock_client.get_running_timer.return_value = {"id": "timer1"}
        result = runner.invoke(time_group, ['stop'])
        
        assert "Timer stopped" in result.output
        mock_client.stop_timer.assert_called_once()

def test_time_stop_with_task_id(runner, mock_config, mock_client):
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config), \
         patch('cupt.time_tracker.ClickUpClient', return_value=mock_client):
        
        mock_client.get_running_timer.return_value = {"id": "timer1"}
        result = runner.invoke(time_group, ['stop', 'task1'])
        
        assert result.exit_code == 0
        assert "Timer stopped" in result.output
        mock_client.stop_timer.assert_called_once()

def test_time_status_running(runner, mock_config, mock_client):
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config), \
         patch('cupt.time_tracker.ClickUpClient', return_value=mock_client):
        
        mock_client.get_running_timer.return_value = {
            "task_id": "abc",
            "start": 1600000000000
        }
        result = runner.invoke(time_group, ['status'])
        
        assert "Timer is running" in result.output
        assert "abc" in result.output

def test_time_add_success(runner, mock_config, mock_client):
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config), \
         patch('cupt.time_tracker.ClickUpClient', return_value=mock_client):
        
        result = runner.invoke(time_group, ['add', 'task1', '1h', '-m', 'work'])
        assert result.exit_code == 0
        assert "Added 1h to task task1" in result.output
        mock_client.add_time_entry.assert_called_once()

def test_time_auth_error(runner):
    mock_config = MagicMock()
    mock_config.is_authenticated.return_value = False
    with patch('cupt.time_tracker.ConfigManager', return_value=mock_config):
        result = runner.invoke(time_group, ['start', 'task1'])
        assert "Not authenticated" in result.output
