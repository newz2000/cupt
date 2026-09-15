"""Tests for TypeService and the `cupt types` command."""

import json
from unittest.mock import MagicMock, patch

import pytest

from cupt.services.type_service import TypeService
from cupt.task_types import types_cmd

# ---------------------------------------------------------------------------
# TypeService
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def service(mock_client):
    return TypeService(mock_client)


def test_list_types_synthesizes_default_task_first(service, mock_client):
    """The default 'Task' type (id 0) leads the list, even though ClickUp's
    endpoint never returns it."""
    mock_client.get_custom_item_types.return_value = [
        {"id": 1002, "name": "Milestone", "description": "A milestone"},
    ]
    types = service.list_types("ws1")
    assert types[0] == {"id": 0, "name": "Task", "description": "Default ClickUp task"}
    assert types[1]["id"] == 1002
    assert types[1]["name"] == "Milestone"


def test_list_types_is_memoized(service, mock_client):
    """A second call within the same service instance costs no second API
    call."""
    mock_client.get_custom_item_types.return_value = [
        {"id": 1002, "name": "Milestone", "description": None},
    ]
    first = service.list_types("ws1")
    second = service.list_types("ws1")
    assert first == second
    mock_client.get_custom_item_types.assert_called_once()


def test_resolve_names_case_insensitive(service, mock_client):
    mock_client.get_custom_item_types.return_value = [
        {"id": 1002, "name": "Milestone", "description": None},
    ]
    assert service.resolve_names("ws1", ["MILESTONE"]) == [1002]


def test_resolve_names_handles_name_with_space(service, mock_client):
    mock_client.get_custom_item_types.return_value = [
        {"id": 5, "name": "Corp Matter", "description": None},
    ]
    assert service.resolve_names("ws1", ["Corp Matter"]) == [5]


def test_resolve_names_task_resolves_to_zero(service, mock_client):
    mock_client.get_custom_item_types.return_value = []
    assert service.resolve_names("ws1", ["Task"]) == [0]


def test_resolve_names_unknown_raises_and_lists_valid(service, mock_client):
    mock_client.get_custom_item_types.return_value = [
        {"id": 1002, "name": "Milestone", "description": None},
    ]
    with pytest.raises(ValueError) as excinfo:
        service.resolve_names("ws1", ["Bogus"])
    message = str(excinfo.value)
    assert "Bogus" in message
    assert "Task" in message
    assert "Milestone" in message


def test_name_for_maps_id_to_name(service, mock_client):
    mock_client.get_custom_item_types.return_value = [
        {"id": 1002, "name": "Milestone", "description": None},
    ]
    assert service.name_for("ws1", 1002) == "Milestone"


def test_name_for_none_is_default_type(service, mock_client):
    mock_client.get_custom_item_types.return_value = []
    assert service.name_for("ws1", None) == "Task"


def test_name_for_undefined_id_returns_none(service, mock_client):
    mock_client.get_custom_item_types.return_value = []
    assert service.name_for("ws1", 9999) is None


# ---------------------------------------------------------------------------
# `cupt types` CLI
# ---------------------------------------------------------------------------


def _ctx(mock_config, mock_client, workspace_id="workspace1"):
    return (mock_config, mock_client, workspace_id)


def test_types_cmd_human_output(runner, mock_config, mock_client):
    with patch(
        "cupt.task_types.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_custom_item_types.return_value = [
            {"id": 1002, "name": "Milestone", "description": "A milestone"},
        ]
        result = runner.invoke(types_cmd)
        assert result.exit_code == 0
        assert "Task" in result.output
        assert "Milestone" in result.output


def test_types_cmd_json_output(runner, mock_config, mock_client):
    with patch(
        "cupt.task_types.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_custom_item_types.return_value = [
            {"id": 1002, "name": "Milestone", "description": "A milestone"},
        ]
        result = runner.invoke(types_cmd, ["--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0] == {
            "id": 0,
            "name": "Task",
            "description": "Default ClickUp task",
        }
        assert data[1]["name"] == "Milestone"


def test_types_cmd_unauthenticated_exits_2(runner):
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        result = runner.invoke(types_cmd)
        assert result.exit_code == 2
