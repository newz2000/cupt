import pytest
from unittest.mock import MagicMock, patch
from cupt.services.task_service import TaskService

@pytest.fixture
def mock_client():
    return MagicMock()

@pytest.fixture
def service(mock_client):
    return TaskService(mock_client)

def test_get_filters_base(service):
    filters = service.get_filters()
    assert filters['subtasks'] == 'true'
    assert filters['include_subtasks'] == 'true'

def test_list_tasks_filtering(service, mock_client):
    mock_client.get_team_tasks.return_value = [
        {"id": "t1", "status": {"type": "open"}},
        {"id": "t2", "status": {"type": "closed"}}
    ]
    
    # Test open only
    tasks = service.list_tasks("team1", include_closed=False)
    assert len(tasks) == 1
    assert tasks[0]["id"] == "t1"
    
    # Test include closed
    tasks = service.list_tasks("team1", include_closed=True)
    assert len(tasks) == 2

def test_resolve_parent_names(service, mock_client):
    tasks = [{"id": "s1", "parent": "p1"}]
    mock_client.get_tasks_by_ids.return_value = [{"id": "p1", "name": "Parent Name"}]
    
    cache = {}
    service.resolve_parent_names("team1", tasks, cache)
    
    assert cache["p1"] == "Parent Name"
    mock_client.get_tasks_by_ids.assert_called_with("team1", ["p1"])

def test_get_task_context(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "parent": "p1", "name": "Task 1"}
    mock_client.get_task_comments.return_value = []
    mock_client._make_request.return_value = {"tasks": []}
    
    ctx = service.get_task_context("t1", "team1")
    
    assert ctx["task"]["id"] == "t1"
    assert ctx["is_subtask"] is True
    mock_client.get_task.assert_any_call("t1")
    mock_client.get_task_comments.assert_called_with("t1")
