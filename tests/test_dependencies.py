import json
from unittest.mock import MagicMock, patch

import pytest

from cupt.dependencies import dep_group
from cupt.errors import EXIT_API
from cupt.exceptions import APIError
from cupt.services.dependency_service import DependencyService


def _ctx(mock_config, mock_client, team_id="team1"):
    return (mock_config, mock_client, team_id)


# ---------------------------------------------------------------------
# DependencyService
# ---------------------------------------------------------------------


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def service(mock_client):
    return DependencyService(mock_client)


def test_list_dependencies_direction_ignores_type_field(service, mock_client):
    """Direction must come from task_id/depends_on, never from `type`.

    Both entries carry the same `type` value (1), which the ticket that
    requested this feature says was never confirmed to mean anything in
    particular. If a future change branches on `type` instead of the
    structural task_id/depends_on comparison, this test flips: the "waiting
    on" entry would end up in `blocking` and vice versa.
    """
    mock_client.get_task.side_effect = lambda task_id: {
        "main": {
            "id": "main",
            "dependencies": [
                # main waits on "blocker" -- same `type` as the other entry.
                {"task_id": "main", "depends_on": "blocker", "type": 1},
                # "blocked" waits on main -- i.e. main blocks it.
                {"task_id": "blocked", "depends_on": "main", "type": 1},
            ],
        },
        "blocker": {
            "id": "blocker",
            "name": "Blocker task",
            "status": {"status": "open", "type": "open"},
        },
        "blocked": {
            "id": "blocked",
            "name": "Blocked task",
            "status": {"status": "open", "type": "open"},
        },
    }[task_id]

    result = service.list_dependencies("main")

    assert [e["id"] for e in result["waiting_on"]] == ["blocker"]
    assert result["waiting_on"][0]["name"] == "Blocker task"
    assert [e["id"] for e in result["blocking"]] == ["blocked"]
    assert result["blocking"][0]["name"] == "Blocked task"


def test_list_dependencies_blocked_true_when_blocker_unfinished(service, mock_client):
    mock_client.get_task.side_effect = lambda task_id: {
        "main": {
            "id": "main",
            "dependencies": [
                {"task_id": "main", "depends_on": "blocker", "type": 1},
            ],
        },
        "blocker": {
            "id": "blocker",
            "name": "Blocker task",
            "status": {"status": "in progress", "type": "open"},
        },
    }[task_id]

    result = service.list_dependencies("main")

    assert result["blocked"] is True
    assert result["waiting_on"][0]["complete"] is False


@pytest.mark.parametrize("status_type", ["done", "closed"])
def test_list_dependencies_not_blocked_when_all_blockers_done(
    service, mock_client, status_type
):
    mock_client.get_task.side_effect = lambda task_id: {
        "main": {
            "id": "main",
            "dependencies": [
                {"task_id": "main", "depends_on": "blocker", "type": 1},
            ],
        },
        "blocker": {
            "id": "blocker",
            "name": "Blocker task",
            "status": {"status": "done", "type": status_type},
        },
    }[task_id]

    result = service.list_dependencies("main")

    assert result["blocked"] is False
    assert result["waiting_on"][0]["complete"] is True


def test_list_dependencies_empty(service, mock_client):
    mock_client.get_task.return_value = {"id": "main", "dependencies": []}

    result = service.list_dependencies("main")

    assert result == {
        "task_id": "main",
        "waiting_on": [],
        "blocking": [],
        "blocked": False,
    }


def test_list_dependencies_degrades_when_linked_task_fetch_fails(service, mock_client):
    def _get_task(task_id):
        if task_id == "main":
            return {
                "id": "main",
                "dependencies": [
                    {"task_id": "main", "depends_on": "gone", "type": 1},
                ],
            }
        raise APIError("HTTP 404")

    mock_client.get_task.side_effect = _get_task

    result = service.list_dependencies("main")

    assert result["waiting_on"] == [
        {"id": "gone", "name": None, "status": None, "complete": False}
    ]
    assert result["blocked"] is True


def test_add_dependency_calls_client(service, mock_client):
    service.add_dependency("t1", "t2")
    mock_client.add_task_dependency.assert_called_once_with("t1", "t2")


def test_remove_dependency_calls_client(service, mock_client):
    service.remove_dependency("t1", "t2")
    mock_client.remove_task_dependency.assert_called_once_with("t1", "t2")


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def test_dep_list_json(runner, mock_config, mock_client):
    mock_client.get_task.side_effect = lambda task_id: {
        "main": {
            "id": "main",
            "dependencies": [
                {"task_id": "main", "depends_on": "blocker", "type": 1},
            ],
        },
        "blocker": {
            "id": "blocker",
            "name": "Blocker task",
            "status": {"status": "open", "type": "open"},
        },
    }[task_id]

    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["list", "main", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["task_id"] == "main"
    assert payload["blocked"] is True
    assert payload["waiting_on"][0]["id"] == "blocker"


def test_dep_list_human_no_dependencies(runner, mock_config, mock_client):
    mock_client.get_task.return_value = {"id": "main", "dependencies": []}

    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["list", "main"])

    assert result.exit_code == 0
    assert "Waiting on:" in result.output
    assert "Blocking:" in result.output
    assert "(none)" in result.output


def test_dep_list_human_shows_sections(runner, mock_config, mock_client):
    mock_client.get_task.side_effect = lambda task_id: {
        "main": {
            "id": "main",
            "dependencies": [
                {"task_id": "main", "depends_on": "blocker", "type": 1},
                {"task_id": "blocked", "depends_on": "main", "type": 1},
            ],
        },
        "blocker": {
            "id": "blocker",
            "name": "Blocker task",
            "status": {"status": "done", "type": "done"},
        },
        "blocked": {
            "id": "blocked",
            "name": "Blocked task",
            "status": {"status": "open", "type": "open"},
        },
    }[task_id]

    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["list", "main"])

    assert result.exit_code == 0
    assert "Blocker task" in result.output
    assert "Blocked task" in result.output


def test_dep_list_api_error(runner, mock_config, mock_client):
    mock_client.get_task.side_effect = APIError("HTTP 500")

    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["list", "main"])

    assert result.exit_code == EXIT_API
    assert "Failed to list dependencies" in result.output


def test_dep_add(runner, mock_config, mock_client):
    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["add", "t1", "--waiting-on", "t2"])

    assert result.exit_code == 0
    assert "t1 now waits on t2" in result.output
    mock_client.add_task_dependency.assert_called_once_with("t1", "t2")


def test_dep_add_requires_waiting_on(runner, mock_config, mock_client):
    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["add", "t1"])

    assert result.exit_code != 0
    mock_client.add_task_dependency.assert_not_called()


def test_dep_add_api_error(runner, mock_config, mock_client):
    mock_client.add_task_dependency.side_effect = APIError("HTTP 500")

    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["add", "t1", "--waiting-on", "t2"])

    assert result.exit_code == EXIT_API
    assert "Failed to add dependency" in result.output


def test_dep_rm(runner, mock_config, mock_client):
    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["rm", "t1", "--waiting-on", "t2"])

    assert result.exit_code == 0
    assert "t1 no longer waits on t2" in result.output
    mock_client.remove_task_dependency.assert_called_once_with("t1", "t2")


def test_dep_rm_api_error(runner, mock_config, mock_client):
    mock_client.remove_task_dependency.side_effect = APIError("HTTP 500")

    with patch(
        "cupt.dependencies.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        result = runner.invoke(dep_group, ["rm", "t1", "--waiting-on", "t2"])

    assert result.exit_code == EXIT_API
    assert "Failed to remove dependency" in result.output
