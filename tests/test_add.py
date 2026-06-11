"""Tests for `cupt add` — quick task capture for interactive users and agents."""

import json
from unittest.mock import patch

import pytest

from cupt.add import add_cmd
from cupt.state import StateManager
from cupt.utils import set_interactive_override


@pytest.fixture
def interactive():
    set_interactive_override(True)
    yield
    set_interactive_override(None)


@pytest.fixture
def non_interactive():
    set_interactive_override(False)
    yield
    set_interactive_override(None)


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    original_init = StateManager.__init__

    def patched_init(self, p=None):
        original_init(self, state_path if p is None else p)

    monkeypatch.setattr(StateManager, "__init__", patched_init)
    return state_path


def _ctx(mock_config, mock_client):
    return (mock_config, mock_client, "workspace1")


def _config_get(values):
    """Helper to build a side_effect for mock_config.get."""

    def fn(key, default=None):
        return values.get(key, default)

    return fn


# ---------------------------------------------------------------------------
# minimal happy path
# ---------------------------------------------------------------------------


def test_add_minimal_with_default_list(
    runner, mock_config, mock_client, non_interactive, isolated_state
):
    """Non-interactive: --list comes from config.user.default_list_id."""
    mock_config.get.side_effect = _config_get(
        {
            "user.user_id": "u1",
            "user.default_list_id": "list42",
        }
    )
    mock_client.create_task.return_value = {"id": "tNEW", "url": "..."}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Z task"])

    assert result.exit_code == 0
    assert "Created task tNEW" in result.output
    mock_client.create_task.assert_called_once()
    list_id, payload = mock_client.create_task.call_args[0]
    assert list_id == "list42"
    assert payload["name"] == "Z task"
    # user_id "u1" isn't an int — silently dropped from assignees rather than
    # failing the create. ClickUp returns an unassigned task in that case.
    assert "assignees" not in payload


def test_add_uses_active_task_list_in_interactive(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """Interactive: list inferred from the active task before falling back to config."""
    StateManager().set_active("868active", "Active task")
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "fallback_list"}
    )
    mock_client.get_task.return_value = {
        "id": "868active",
        "list": {"id": "active_list"},
    }
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Captured idea"])

    assert result.exit_code == 0
    list_id, _ = mock_client.create_task.call_args[0]
    assert list_id == "active_list"


def test_add_falls_back_to_config_when_no_active(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """Interactive with no active task → user.default_list_id."""
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "fallback_list"}
    )
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Captured idea"])

    assert result.exit_code == 0
    list_id, _ = mock_client.create_task.call_args[0]
    assert list_id == "fallback_list"


def test_add_errors_when_no_list_resolvable(
    runner, mock_config, mock_client, non_interactive, isolated_state
):
    mock_config.get.side_effect = _config_get({"user.user_id": "100"})

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["X"])

    assert "No list specified" in result.output
    mock_client.create_task.assert_not_called()


# ---------------------------------------------------------------------------
# --blocks (bare flag, sentinel, explicit ID, short ID)
# ---------------------------------------------------------------------------


def test_blocks_this_uses_active(
    runner, mock_config, mock_client, interactive, isolated_state
):
    StateManager().set_active("868active", "Active")
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "list42"}
    )
    mock_client.get_task.return_value = {
        "id": "868active",
        "list": {"id": "active_list"},
    }
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Blocker", "--blocks", "this"])

    assert result.exit_code == 0
    mock_client.add_task_dependency.assert_called_once_with(
        "868active", depends_on="tNEW"
    )
    assert "blocks 868active" in result.output


def test_blocks_explicit_id(
    runner, mock_config, mock_client, interactive, isolated_state
):
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "list42"}
    )
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Blocker", "--blocks", "868other"])

    assert result.exit_code == 0
    mock_client.add_task_dependency.assert_called_once_with(
        "868other", depends_on="tNEW"
    )


def test_blocks_short_id_resolves(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """`--blocks 3` should resolve through the short-ID table."""
    state = StateManager()
    state.reconcile([{"id": "868target", "name": "Target"}])
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "list42"}
    )
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Blocker", "--blocks", "1"])

    assert result.exit_code == 0
    mock_client.add_task_dependency.assert_called_once_with(
        "868target", depends_on="tNEW"
    )


def test_blocks_this_without_active_errors(
    runner, mock_config, mock_client, interactive, isolated_state
):
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "list42"}
    )

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Blocker", "--blocks", "this"])

    assert "needs an active task" in result.output
    mock_client.create_task.assert_not_called()


# ---------------------------------------------------------------------------
# --parent (same semantics, via payload "parent" field)
# ---------------------------------------------------------------------------


def test_parent_this_uses_active(
    runner, mock_config, mock_client, interactive, isolated_state
):
    StateManager().set_active("868parent", "Parent")
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "list42"}
    )
    mock_client.get_task.return_value = {"id": "868parent", "list": {"id": "L"}}
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Subtask", "--parent", "this"])

    assert result.exit_code == 0
    _, payload = mock_client.create_task.call_args[0]
    assert payload["parent"] == "868parent"
    assert "subtask of 868parent" in result.output


def test_parent_explicit_id_does_not_need_active(
    runner, mock_config, mock_client, non_interactive, isolated_state
):
    """Hermes can use --parent <id> without any active task setup."""
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "L"}
    )
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["S", "--parent", "868p"])

    assert result.exit_code == 0
    _, payload = mock_client.create_task.call_args[0]
    assert payload["parent"] == "868p"


# ---------------------------------------------------------------------------
# extras: description, due, tags, json
# ---------------------------------------------------------------------------


def test_description_due_and_tags(
    runner, mock_config, mock_client, non_interactive, isolated_state
):
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "L"}
    )
    mock_client.create_task.return_value = {"id": "tNEW"}

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(
            add_cmd,
            [
                "X",
                "-d",
                "the description",
                "--due",
                "2026-12-31",
                "--tag",
                "urgent",
                "--tag",
                "api",
            ],
        )

    assert result.exit_code == 0
    _, payload = mock_client.create_task.call_args[0]
    assert payload["description"] == "the description"
    assert payload["tags"] == ["urgent", "api"]
    assert payload["due_date"] > 0  # ms epoch
    assert payload["due_date_time"] is True


def test_due_invalid_errors(
    runner, mock_config, mock_client, non_interactive, isolated_state
):
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "L"}
    )

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["X", "--due", "nope"])

    assert "Could not parse due date" in result.output
    mock_client.create_task.assert_not_called()


def test_json_output(runner, mock_config, mock_client, non_interactive, isolated_state):
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "L"}
    )
    mock_client.create_task.return_value = {
        "id": "tNEW",
        "url": "https://...",
        "name": "X",
    }

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["X", "--json"])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert parsed["id"] == "tNEW"


# ---------------------------------------------------------------------------
# dependency-add failure shouldn't fail the whole command
# ---------------------------------------------------------------------------


def test_dependency_failure_warns_but_keeps_task(
    runner, mock_config, mock_client, interactive, isolated_state
):
    StateManager().set_active("868active", "Active")
    mock_config.get.side_effect = _config_get(
        {"user.user_id": "100", "user.default_list_id": "L"}
    )
    mock_client.get_task.return_value = {"id": "868active", "list": {"id": "L"}}
    mock_client.create_task.return_value = {"id": "tNEW"}
    mock_client.add_task_dependency.side_effect = RuntimeError("workspace disabled")

    with patch(
        "cupt.add.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_cmd, ["Blocker", "--blocks", "this"])

    assert result.exit_code == 0
    assert "Task created (tNEW)" in result.output
    assert "failed to add dependency" in result.output
