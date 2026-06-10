"""Integration tests for cupt start / stop / active and active-task fallback."""

from unittest.mock import MagicMock, patch

import pytest

from cupt.active import active_cmd, start_cmd, stop_cmd
from cupt.notes import add_note
from cupt.state import StateManager
from cupt.tasks import complete_task_cmd, show_task_cmd
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
    """Redirect StateManager's default path into a fresh tmp dir so tests
    never touch the real ~/.cupt/state.json."""
    state_path = tmp_path / "state.json"
    original_init = StateManager.__init__

    def patched_init(self, p=None):
        original_init(self, state_path if p is None else p)

    monkeypatch.setattr(StateManager, "__init__", patched_init)
    return state_path


def _ctx(mock_config, mock_client):
    return (mock_config, mock_client, "workspace1")


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_start_sets_active_task(
    runner, mock_config, mock_client, interactive, isolated_state
):
    mock_client.get_task.return_value = {"id": "868abc", "name": "Fix login"}
    with patch(
        "cupt.active.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(start_cmd, ["868abc"])

    assert result.exit_code == 0
    assert "Active: 868abc" in result.output
    assert StateManager().get_active()["clickup_id"] == "868abc"


def test_start_warns_on_replace(
    runner, mock_config, mock_client, interactive, isolated_state
):
    StateManager().set_active("868old", "Previous")
    mock_client.get_task.return_value = {"id": "868new", "name": "New task"}
    with patch(
        "cupt.active.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(start_cmd, ["868new"])

    assert "Replaced active task 868old" in result.output


def test_start_blocked_in_non_interactive(runner, non_interactive, isolated_state):
    result = runner.invoke(start_cmd, ["868abc"])
    assert "interactive-only" in result.output
    assert not isolated_state.exists()


def test_start_resolves_short_id(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """`cupt start 3` resolves via the short-ID table just like other commands."""
    state = StateManager()
    state.reconcile([{"id": "868target", "name": "Target"}])
    mock_client.get_task.return_value = {"id": "868target", "name": "Target"}
    with patch(
        "cupt.active.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(start_cmd, ["1"])

    assert result.exit_code == 0
    assert StateManager().get_active()["clickup_id"] == "868target"


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def test_stop_clears_active(runner, interactive, isolated_state):
    StateManager().set_active("868abc", "Working")
    result = runner.invoke(stop_cmd)
    assert "Stopped: 868abc" in result.output
    assert StateManager().get_active() is None


def test_stop_warns_when_nothing_active(runner, interactive, isolated_state):
    result = runner.invoke(stop_cmd)
    assert "No active task" in result.output


# ---------------------------------------------------------------------------
# active
# ---------------------------------------------------------------------------


def test_active_shows_current(runner, interactive, isolated_state):
    StateManager().set_active("868abc", "Working")
    result = runner.invoke(active_cmd)
    assert "868abc" in result.output
    assert "Working" in result.output


def test_active_silent_in_non_interactive(runner, non_interactive, isolated_state):
    StateManager().set_active("868abc", "Working")
    result = runner.invoke(active_cmd)
    assert result.exit_code == 0
    # Silent — no leak of active task to script consumers
    assert "868abc" not in result.output


# ---------------------------------------------------------------------------
# active-task fallback in note / show / done
# ---------------------------------------------------------------------------


def test_note_falls_back_to_active(
    runner, mock_config, mock_client, interactive, isolated_state
):
    StateManager().set_active("868abc", "Working")
    with patch(
        "cupt.notes.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_note, ["My note text"])

    assert result.exit_code == 0
    assert "Note added to task 868abc" in result.output


def test_note_two_args_still_works(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """Backwards compatibility: `cupt note <id> <text>` still works."""
    with patch(
        "cupt.notes.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(add_note, ["868explicit", "Note text"])

    assert result.exit_code == 0
    assert "Note added to task 868explicit" in result.output


def test_done_clears_active_and_frees_short_id(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """Completing the active task clears the pointer + frees its short ID."""
    state = StateManager()
    state.reconcile([{"id": "868abc", "name": "Active"}])
    state.set_active("868abc", "Active")

    # Patch TaskService.complete_task to succeed without API calls.
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.tasks.TaskService") as MockSvc:
        instance = MockSvc.return_value
        instance.complete_task.return_value = "complete"
        result = runner.invoke(complete_task_cmd, ["868abc"])

    assert result.exit_code == 0
    fresh = StateManager()
    assert fresh.get_active() is None
    assert fresh.short_id_for("868abc") is None


def test_done_does_not_clear_unrelated_active(
    runner, mock_config, mock_client, interactive, isolated_state
):
    """Closing some other task should not clobber the active pointer."""
    state = StateManager()
    state.set_active("868current", "Current")

    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.tasks.TaskService") as MockSvc:
        instance = MockSvc.return_value
        instance.complete_task.return_value = "complete"
        runner.invoke(complete_task_cmd, ["868other"])

    assert StateManager().get_active()["clickup_id"] == "868current"


def test_show_falls_back_to_active(
    runner, mock_config, mock_client, interactive, isolated_state
):
    StateManager().set_active("868abc", "Working")
    mock_client.get_task.return_value = {
        "id": "868abc",
        "name": "Working",
        "status": {"status": "open"},
    }
    mock_client.get_task_comments.return_value = []
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(show_task_cmd, [])

    assert result.exit_code == 0
    assert "868abc" in result.output


def test_show_without_arg_non_interactive_errors(
    runner, mock_config, mock_client, non_interactive, isolated_state
):
    """Scripts must pass an explicit ID — active task is invisible to them."""
    StateManager().set_active("868abc", "Working")  # set but inert
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(show_task_cmd, [])

    assert "Task ID required" in result.output
