import pytest
from unittest.mock import MagicMock, patch
from cupt.tasks import list_tasks_cmd, show_task_cmd, complete_task_cmd, context_cmd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(mock_config, mock_client, team_id="team1"):
    """Return a get_client_context return value tuple."""
    return (mock_config, mock_client, team_id)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_tasks_cli(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_team_tasks.return_value = [
            {"id": "t1", "name": "Task 1", "status": {"status": "open", "type": "open"}}
        ]
        result = runner.invoke(list_tasks_cmd)
        assert result.exit_code == 0
        assert "Task 1" in result.output


def test_list_tasks_filters(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_team_tasks.return_value = []
        for flag in ["--overdue", "--today", "--week"]:
            result = runner.invoke(list_tasks_cmd, [flag])
            assert result.exit_code == 0


def test_list_tasks_hide_subtasks(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_team_tasks.return_value = [
            {"id": "t1", "name": "Top Task", "status": {"status": "open", "type": "open"}},
            {"id": "t2", "name": "Sub Task", "parent": "t1", "status": {"status": "open", "type": "open"}},
        ]
        result = runner.invoke(list_tasks_cmd, ["--hide-subtasks"])
        assert result.exit_code == 0
        assert "Top Task" in result.output
        assert "Sub Task" not in result.output


def test_list_tasks_limit(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_team_tasks.return_value = [
            {"id": f"t{i}", "name": f"Task {i}", "status": {"status": "open", "type": "open"}}
            for i in range(5)
        ]
        result = runner.invoke(list_tasks_cmd, ["-n", "2"])
        assert result.exit_code == 0
        assert "Task 0" in result.output
        assert "Task 1" in result.output
        assert "Task 4" not in result.output


def test_list_tasks_shows_parent_name(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_team_tasks.return_value = [
            {"id": "s1", "name": "Sub Task", "parent": "p1", "status": {"status": "open", "type": "open"}},
        ]
        mock_client.get_tasks_by_ids.return_value = []
        mock_client.get_task.return_value = {"id": "p1", "name": "Parent Task"}
        result = runner.invoke(list_tasks_cmd)
        assert result.exit_code == 0
        assert "Parent Task" in result.output
        assert "sub of" in result.output


def test_list_tasks_exception(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_team_tasks.side_effect = Exception("API Error")
        result = runner.invoke(list_tasks_cmd)
        assert "Failed to list tasks" in result.output


def test_list_tasks_no_team_id(runner, mock_client):
    """list_tasks prints its own error when team_id is absent (uses need_team=False)."""
    no_team_config = MagicMock()
    no_team_config.is_authenticated.return_value = True
    no_team_config.get.return_value = None
    with patch("cupt.tasks.get_client_context", return_value=(no_team_config, mock_client, None)):
        result = runner.invoke(list_tasks_cmd)
        assert "Team ID not set" in result.output


def test_tasks_auth_error(runner):
    """Auth guard in get_client_context prints the error before returning None."""
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        result = runner.invoke(list_tasks_cmd)
        assert "Not authenticated" in result.output


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def test_show_task_cli(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {
            "id": "t1", "name": "Task 1", "status": {"status": "open"},
            "space": {"id": "s1"}, "folder": {"name": "f1"}, "list": {"name": "l1"},
            "description": "test desc",
        }
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Task 1" in result.output
        assert "test desc" in result.output


def test_show_task_with_parent(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.side_effect = [
            {"id": "t1", "name": "Child Task", "status": {"status": "open"},
             "parent": "p1", "space": {"id": "s1"}, "folder": {"name": "f1"}, "list": {"name": "l1"}},
            {"id": "p1", "name": "Parent Task"},
        ]
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Parent Task" in result.output


def test_show_task_with_notes(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {
            "id": "t1", "name": "Task 1", "status": {"status": "open"},
            "space": {"id": "s1"}, "folder": {"name": "f1"}, "list": {"name": "l1"},
        }
        mock_client.get_task_comments.return_value = [
            {"user": {"username": "alice"}, "text": "A comment", "date": None}
        ]
        result = runner.invoke(show_task_cmd, ["t1", "--notes"])
        assert result.exit_code == 0
        assert "A comment" in result.output
        assert "alice" in result.output


# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------

def test_complete_task_cli(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
        mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Task t1 marked as 'Done'" in result.output


def test_complete_task_no_list_id(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {"id": "t1", "list": {}}
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert "Could not find list" in result.output


def test_complete_task_fallback_to_space_statuses(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}, "space": {"id": "s1"}}
        mock_client.get_list_statuses.return_value = []
        mock_client.get_space_statuses.return_value = [{"status": "Done", "type": "closed"}]
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Done" in result.output


def test_complete_task_with_note(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
        mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
        result = runner.invoke(complete_task_cmd, ["t1", "--note", "All done"])
        assert result.exit_code == 0
        mock_client.add_task_comment.assert_called_once_with("t1", "All done")


def test_complete_task_exception(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.side_effect = Exception("API Error")
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert "Failed to complete task" in result.output


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def test_context_cmd_cli(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.side_effect = [
            {"id": "t1", "name": "Task 1", "parent": "p1", "status": {"status": "open"}},
            {"id": "p1", "name": "Parent", "status": {"status": "open"}},
        ]
        mock_client.get_task_comments.return_value = []
        mock_client.get_task_children.return_value = [
            {"id": "t1", "name": "Task 1", "status": {"status": "open"}}
        ]
        result = runner.invoke(context_cmd, ["t1"])
        assert result.exit_code == 0
        assert "PARENT TASK" in result.output
        assert "SIBLINGS" in result.output


def test_context_cmd_top_level(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.return_value = {"id": "t1", "name": "Top Task", "status": {"status": "open"}}
        mock_client.get_task_comments.return_value = [{"user": {"username": "bob"}, "text": "A note"}]
        mock_client.get_task_children.return_value = []
        result = runner.invoke(context_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Top Level Task" in result.output
        assert "A note" in result.output


def test_context_cmd_exception(runner, mock_config, mock_client):
    with patch("cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)):
        mock_client.get_task.side_effect = Exception("API Error")
        result = runner.invoke(context_cmd, ["t1"])
        assert "Failed to show context" in result.output
