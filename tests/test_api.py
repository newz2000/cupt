import pytest
from unittest.mock import MagicMock, patch
from cupt.api import ClickUpClient

@pytest.fixture
def mock_session():
    with patch('requests.Session') as mock:
        yield mock.return_value

@pytest.fixture
def client(mock_session):
    return ClickUpClient("test_token")

def test_get_user(client, mock_session):
    mock_session.get.return_value.json.return_value = {"user": {"username": "testuser"}}
    mock_session.get.return_value.status_code = 200
    
    user = client.get_user()
    assert user["user"]["username"] == "testuser"
    mock_session.get.assert_called_once()

def test_get_teams(client, mock_session):
    mock_session.get.return_value.json.return_value = {"teams": [{"id": "123", "name": "Team 1"}]}
    mock_session.get.return_value.status_code = 200
    
    teams = client.get_teams()
    assert len(teams) == 1
    assert teams[0]["name"] == "Team 1"

def test_get_team_tasks(client, mock_session):
    mock_session.get.return_value.json.return_value = {"tasks": [{"id": "abc", "name": "Task 1"}]}
    mock_session.get.return_value.status_code = 200
    
    tasks = client.get_team_tasks("123", {"archived": "false"})
    assert len(tasks) == 1
    assert tasks[0]["id"] == "abc"
    
    # Verify params were passed
    args, kwargs = mock_session.get.call_args
    assert kwargs['params']['archived'] == "false"

def test_get_tasks_by_ids(client, mock_session):
    mock_session.get.return_value.json.return_value = {"tasks": [{"id": "t1"}]}
    mock_session.get.return_value.status_code = 200
    
    res = client.get_tasks_by_ids("team1", ["t1", "t2"])
    assert len(res) == 1
    assert "ids[]" in mock_session.get.call_args[1]['params']

def test_update_task(client, mock_session):
    mock_session.put.return_value.json.return_value = {"id": "t1"}
    mock_session.put.return_value.status_code = 200
    
    res = client.update_task("t1", {"status": "done"})
    assert res["id"] == "t1"
    mock_session.put.assert_called_once()

def test_timer_methods(client, mock_session):
    # Start
    mock_session.post.return_value.json.return_value = {"id": "entry1"}
    mock_session.post.return_value.status_code = 200
    client.start_timer("team1", "task1")
    
    # Stop
    client.stop_timer("team1")
    
    # Current
    mock_session.get.return_value.json.return_value = {"data": {"id": "entry1"}}
    res = client.get_running_timer("team1")
    assert res["id"] == "entry1"

def test_add_time_entry(client, mock_session):
    mock_session.post.return_value.json.return_value = {"id": "new_entry"}
    mock_session.post.return_value.status_code = 200
    res = client.add_time_entry("team1", "task1", 3600000, "desc")
    assert res["id"] == "new_entry"

def test_hierarchy_methods(client, mock_session):
    # Spaces
    mock_session.get.return_value.json.return_value = {"spaces": [{"id": "s1"}]}
    assert client.get_spaces("team1")[0]["id"] == "s1"
    
    # Lists
    mock_session.get.return_value.json.return_value = {"lists": [{"id": "l1"}]}
    assert client.get_lists("space1")[0]["id"] == "l1"

def test_api_error_handling(client, mock_session):
    import requests
    mock_session.get.return_value.status_code = 401
    mock_session.get.return_value.text = "Unauthorized"
    mock_session.get.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_session.get.return_value)
    
    with pytest.raises(Exception) as excinfo:
        client.get_user()
    assert "HTTP 401" in str(excinfo.value)
