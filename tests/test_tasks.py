import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from cupt.tasks import list_tasks_cmd, show_task_cmd, complete_task_cmd, context_cmd

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def mock_config():
    config = MagicMock()
    config.is_authenticated.return_value = True
    config.get.side_effect = lambda key, default=None: {
        'user.team_id': 'team1',
        'user.user_id': 'user1',
        'auth.access_token': 'token123'
    }.get(key, default)
    config.load_cache.return_value = {}
    return config

@pytest.fixture
def mock_client():
    return MagicMock()

def test_list_tasks_cli(runner, mock_config, mock_client):
    with patch('cupt.tasks.ConfigManager', return_value=mock_config), \
         patch('cupt.tasks.ClickUpClient', return_value=mock_client):
        
        mock_client.get_team_tasks.return_value = [{"id": "t1", "name": "Task 1", "status": {"status": "open", "type": "open"}}]
        
        result = runner.invoke(list_tasks_cmd)
        assert result.exit_code == 0
        assert "Task 1" in result.output

def test_list_tasks_filters(runner, mock_config, mock_client):
    with patch('cupt.tasks.ConfigManager', return_value=mock_config), \
         patch('cupt.tasks.ClickUpClient', return_value=mock_client):
        
        mock_client.get_team_tasks.return_value = []
        
        # Test overdue
        result = runner.invoke(list_tasks_cmd, ['--overdue'])
        assert result.exit_code == 0
        
        # Test today
        result = runner.invoke(list_tasks_cmd, ['--today'])
        assert result.exit_code == 0
        
        # Test week
        result = runner.invoke(list_tasks_cmd, ['--week'])
        assert result.exit_code == 0

def test_show_task_cli(runner, mock_config, mock_client):
    with patch('cupt.tasks.ConfigManager', return_value=mock_config), \
         patch('cupt.tasks.ClickUpClient', return_value=mock_client):
        
        mock_client.get_task.return_value = {
            "id": "t1", "name": "Task 1", "status": {"status": "open"},
            "space": {"id": "s1"}, "folder": {"name": "f1"}, "list": {"name": "l1"},
            "description": "test desc"
        }
        
        result = runner.invoke(show_task_cmd, ['t1'])
        assert result.exit_code == 0
        assert "Task 1" in result.output
        assert "test desc" in result.output

def test_complete_task_cli(runner, mock_config, mock_client):
    with patch('cupt.tasks.ConfigManager', return_value=mock_config), \
         patch('cupt.tasks.ClickUpClient', return_value=mock_client):
        
        mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
        # Mocking the internal request for list statuses
        mock_client._make_request.return_value = {"statuses": [{"status": "Done", "type": "closed"}]}
        
        result = runner.invoke(complete_task_cmd, ['t1'])
        assert result.exit_code == 0
        assert "Task t1 marked as 'Done'" in result.output

def test_context_cmd_cli(runner, mock_config, mock_client):
    with patch('cupt.tasks.ConfigManager', return_value=mock_config), \
         patch('cupt.tasks.ClickUpClient', return_value=mock_client):
        
        # Main task
        mock_client.get_task.side_effect = [
            {"id": "t1", "name": "Task 1", "parent": "p1", "status": {"status": "open"}}, # main
            {"id": "p1", "name": "Parent", "status": {"status": "open"}} # parent
        ]
        mock_client.get_task_comments.return_value = []
        # Siblings
        mock_client._make_request.return_value = {"tasks": [{"id": "t1", "name": "Task 1", "status": {"status": "open"}}]}
        
        result = runner.invoke(context_cmd, ['t1'])
        assert result.exit_code == 0
        assert "PARENT TASK" in result.output
        assert "SIBLINGS" in result.output

def test_tasks_auth_error(runner):
    mock_config = MagicMock()
    mock_config.is_authenticated.return_value = False
    with patch('cupt.tasks.ConfigManager', return_value=mock_config):
        result = runner.invoke(list_tasks_cmd)
        assert "Not authenticated" in result.output
