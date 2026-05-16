import json
import time
from unittest.mock import ANY, MagicMock, call, patch

import pytest

from cupt.tasks import (complete_task_cmd, context_cmd, list_tasks_cmd,
                        prefetch_cmd, show_task_cmd)

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
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {"id": "t1", "name": "Task 1", "status": {"status": "open", "type": "open"}}
        ]
        result = runner.invoke(list_tasks_cmd)
        assert result.exit_code == 0
        assert "Task 1" in result.output


def test_list_tasks_filters(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = []
        for flag in ["--overdue", "--today", "--week"]:
            result = runner.invoke(list_tasks_cmd, [flag])
            assert result.exit_code == 0


def test_list_tasks_hide_subtasks(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Top Task",
                "status": {"status": "open", "type": "open"},
            },
            {
                "id": "t2",
                "name": "Sub Task",
                "parent": "t1",
                "status": {"status": "open", "type": "open"},
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--hide-subtasks"])
        assert result.exit_code == 0
        assert "Top Task" in result.output
        assert "Sub Task" not in result.output


def test_list_tasks_limit(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": f"t{i}",
                "name": f"Task {i}",
                "status": {"status": "open", "type": "open"},
            }
            for i in range(5)
        ]
        result = runner.invoke(list_tasks_cmd, ["-n", "2"])
        assert result.exit_code == 0
        assert "Task 0" in result.output
        assert "Task 1" in result.output
        assert "Task 4" not in result.output


def test_list_tasks_shows_parent_name(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "s1",
                "name": "Sub Task",
                "parent": "p1",
                "status": {"status": "open", "type": "open"},
            },
        ]
        mock_client.get_tasks_by_ids.return_value = []
        mock_client.get_task.return_value = {"id": "p1", "name": "Parent Task"}
        result = runner.invoke(list_tasks_cmd)
        assert result.exit_code == 0
        assert "Parent Task" in result.output
        assert "sub of" in result.output


def test_list_tasks_triggers_background_cache(runner, mock_config, mock_client):
    """cupt list silently seeds the detail cache after displaying results."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Task 1",
                "status": {"status": "open", "type": "open"},
            },
        ]
        mock_client.get_task.return_value = {"id": "t1", "name": "Task 1 Full"}
        mock_client.get_task_comments.return_value = []

        result = runner.invoke(list_tasks_cmd)
        assert result.exit_code == 0
        assert "Task 1" in result.output
        mock_config.save_task_detail.assert_called_once_with("t1", ANY)


def test_list_tasks_filter_by_tag(runner, mock_config, mock_client):
    """--tag X keeps only tasks bearing tag X (case-insensitive)."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Has Urgent",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "Urgent"}],
            },
            {
                "id": "t2",
                "name": "No Tags",
                "status": {"status": "open", "type": "open"},
                "tags": [],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--tag", "urgent"])
        assert result.exit_code == 0
        assert "Has Urgent" in result.output
        assert "No Tags" not in result.output


def test_list_tasks_filter_by_no_tag(runner, mock_config, mock_client):
    """--no-tag X drops any task bearing tag X."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Has Waiting",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "waiting"}],
            },
            {
                "id": "t2",
                "name": "Clean Task",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "other"}],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--no-tag", "waiting"])
        assert result.exit_code == 0
        assert "Clean Task" in result.output
        assert "Has Waiting" not in result.output


def test_list_tasks_sends_tags_to_api(runner, mock_config, mock_client):
    """--tag is pushed to the ClickUp API as tags[] (server-side filtering)."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Task 1",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "urgent"}],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--tag", "urgent"])
        assert result.exit_code == 0
        filters = mock_client.get_team_tasks.call_args[0][1]
        assert filters["tags[]"] == ["urgent"]


def test_list_tasks_stacked_tags_or_then_and(runner, mock_config, mock_client):
    """API returns OR'd candidates; client narrows to AND of required tags."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        # Server returns the OR'd candidate set (a OR b).
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Just A",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "a"}],
            },
            {
                "id": "t2",
                "name": "A and B",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "a"}, {"name": "b"}],
            },
            {
                "id": "t3",
                "name": "Just B",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "b"}],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--tag", "a", "--tag", "b"])
        assert result.exit_code == 0
        # API got both tags (OR semantics).
        filters = mock_client.get_team_tasks.call_args[0][1]
        assert set(filters["tags[]"]) == {"a", "b"}
        # Client narrowed to the AND set.
        assert "A and B" in result.output
        assert "Just A" not in result.output
        assert "Just B" not in result.output


def test_list_tasks_tag_filters_stack(runner, mock_config, mock_client):
    """--tag A --tag B requires both; --no-tag C still excludes."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "A only",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "a"}],
            },
            {
                "id": "t2",
                "name": "A and B",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "a"}, {"name": "b"}],
            },
            {
                "id": "t3",
                "name": "A B C",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
            },
        ]
        result = runner.invoke(
            list_tasks_cmd, ["--tag", "a", "--tag", "b", "--no-tag", "c"]
        )
        assert result.exit_code == 0
        assert "A and B" in result.output
        assert "A only" not in result.output
        assert "A B C" not in result.output


def test_list_tasks_tag_filter_no_matches(runner, mock_config, mock_client):
    """A tag filter that matches nothing reports a friendly message."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Task 1",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "alpha"}],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--tag", "missing"])
        assert result.exit_code == 0
        assert "No tasks matched the tag filter" in result.output


def test_list_tasks_json_output(runner, mock_config, mock_client):
    """--json emits a parseable JSON array and suppresses headers + warnings."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Task 1",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "urgent"}],
            },
            {
                "id": "t2",
                "name": "Task 2",
                "status": {"status": "open", "type": "open"},
                "tags": [],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--json"])
        assert result.exit_code == 0
        # Output must be pure JSON — no decorative headers.
        assert "ID" not in result.output.splitlines()[0]
        payload = json.loads(result.output)
        assert isinstance(payload, list)
        assert {t["id"] for t in payload} == {"t1", "t2"}
        # Background caching should NOT run in json mode.
        mock_config.save_task_detail.assert_not_called()


def test_list_tasks_json_respects_tag_filter(runner, mock_config, mock_client):
    """--json + --tag should narrow the JSON payload to matching tasks."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Tagged",
                "status": {"status": "open", "type": "open"},
                "tags": [{"name": "urgent"}],
            },
            {
                "id": "t2",
                "name": "Untagged",
                "status": {"status": "open", "type": "open"},
                "tags": [],
            },
        ]
        result = runner.invoke(list_tasks_cmd, ["--json", "--tag", "urgent"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert [t["id"] for t in payload] == ["t1"]


def test_list_tasks_json_empty(runner, mock_config, mock_client):
    """--json with no matching tasks emits `[]`, not a warning string."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = []
        result = runner.invoke(list_tasks_cmd, ["--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []


def test_list_tasks_exception(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.side_effect = Exception("API Error")
        result = runner.invoke(list_tasks_cmd)
        assert "Failed to list tasks" in result.output


def test_list_tasks_no_team_id(runner, mock_client):
    """list_tasks prints its own error when team_id is absent (uses need_team=False)."""
    no_team_config = MagicMock()
    no_team_config.is_authenticated.return_value = True
    no_team_config.get.return_value = None
    with patch(
        "cupt.tasks.get_client_context",
        return_value=(no_team_config, mock_client, None),
    ):
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
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Task 1",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1"},
            "list": {"name": "l1"},
            "description": "test desc",
        }
        mock_client.get_task_comments.return_value = []
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Task 1" in result.output
        assert "test desc" in result.output


def test_show_task_with_parent(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.side_effect = [
            {
                "id": "t1",
                "name": "Child Task",
                "status": {"status": "open"},
                "parent": "p1",
                "space": {"id": "s1"},
                "folder": {"name": "f1"},
                "list": {"name": "l1"},
            },
            {"id": "p1", "name": "Parent Task"},
        ]
        mock_client.get_task_comments.return_value = []
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Parent Task" in result.output


@pytest.mark.parametrize(
    "task_payload, expected",
    [
        # Two individuals
        (
            {
                "assignees": [{"username": "Matt"}, {"username": "Paweena"}],
                "group_assignees": [],
            },
            "Assignee: Matt, Paweena",
        ),
        # Single individual
        (
            {"assignees": [{"username": "Matt"}], "group_assignees": []},
            "Assignee: Matt",
        ),
        # Team only
        (
            {"assignees": [], "group_assignees": [{"name": "Attorneys"}]},
            "Assignee: Attorneys",
        ),
        # Individual + team
        (
            {
                "assignees": [{"username": "Matt"}],
                "group_assignees": [{"name": "CSMs"}],
            },
            "Assignee: Matt, CSMs",
        ),
        # No assignees
        ({"assignees": [], "group_assignees": []}, "Assignee: Unassigned"),
    ],
)
def test_show_task_assignees(runner, mock_config, mock_client, task_payload, expected):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Task 1",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1"},
            "list": {"name": "l1"},
            **task_payload,
        }
        mock_client.get_task_comments.return_value = []
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert expected in result.output


def test_show_task_with_notes(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Task 1",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1"},
            "list": {"name": "l1"},
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
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
        mock_client.get_list_statuses.return_value = [
            {"status": "Done", "type": "closed"}
        ]
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Task t1 marked as 'Done'" in result.output


def test_complete_task_no_list_id(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {"id": "t1", "list": {}}
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert "Could not find list" in result.output


def test_complete_task_fallback_to_space_statuses(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "list": {"id": "l1"},
            "space": {"id": "s1"},
        }
        mock_client.get_list_statuses.return_value = []
        mock_client.get_space_statuses.return_value = [
            {"status": "Done", "type": "closed"}
        ]
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Done" in result.output


def test_complete_task_with_note(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
        mock_client.get_list_statuses.return_value = [
            {"status": "Done", "type": "closed"}
        ]
        result = runner.invoke(complete_task_cmd, ["t1", "--note", "All done"])
        assert result.exit_code == 0
        mock_client.add_task_comment.assert_called_once_with("t1", "All done")


def test_complete_task_exception(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.side_effect = Exception("API Error")
        result = runner.invoke(complete_task_cmd, ["t1"])
        assert "Failed to complete task" in result.output


def test_complete_task_auto_note_no_ai(runner, mock_config, mock_client):
    """--auto-note shows a graceful warning when no local AI is available."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Write report",
            "list": {"id": "l1"},
        }
        mock_client.get_task_comments.return_value = []
        mock_client.get_list_statuses.return_value = [
            {"status": "Done", "type": "closed"}
        ]
        with patch("cupt.ai.get_ai_suggestion", return_value=None):
            result = runner.invoke(complete_task_cmd, ["t1", "--auto-note"])
            assert result.exit_code == 0
            assert "No local AI available" in result.output
            assert "Done" in result.output  # task still completes


def test_complete_task_auto_note_accepted(runner, mock_config, mock_client):
    """--auto-note completes the task with the AI suggestion when accepted."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Write report",
            "list": {"id": "l1"},
        }
        mock_client.get_task_comments.return_value = []
        mock_client.get_list_statuses.return_value = [
            {"status": "Done", "type": "closed"}
        ]
        with patch("cupt.ai.get_ai_suggestion", return_value="Completed the report."):
            result = runner.invoke(
                complete_task_cmd, ["t1", "--auto-note"], input="a\n"
            )
            assert result.exit_code == 0
            mock_client.add_task_comment.assert_called_once_with(
                "t1", "Completed the report."
            )


def test_complete_task_auto_note_skipped(runner, mock_config, mock_client):
    """--auto-note skips the note when the user enters 's'."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Write report",
            "list": {"id": "l1"},
        }
        mock_client.get_task_comments.return_value = []
        mock_client.get_list_statuses.return_value = [
            {"status": "Done", "type": "closed"}
        ]
        with patch("cupt.ai.get_ai_suggestion", return_value="Completed the report."):
            result = runner.invoke(
                complete_task_cmd, ["t1", "--auto-note"], input="s\n"
            )
            assert result.exit_code == 0
            mock_client.add_task_comment.assert_not_called()


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------


def test_context_cmd_cli(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.side_effect = [
            {
                "id": "t1",
                "name": "Task 1",
                "parent": "p1",
                "status": {"status": "open"},
            },
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
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Top Task",
            "status": {"status": "open"},
        }
        mock_client.get_task_comments.return_value = [
            {"user": {"username": "bob"}, "text": "A note"}
        ]
        mock_client.get_task_children.return_value = []
        result = runner.invoke(context_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Top Level Task" in result.output
        assert "A note" in result.output


def test_context_cmd_exception(runner, mock_config, mock_client):
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.side_effect = Exception("API Error")
        result = runner.invoke(context_cmd, ["t1"])
        assert "Failed to show context" in result.output


# ---------------------------------------------------------------------------
# show --offline
# ---------------------------------------------------------------------------


def test_show_task_saves_detail_cache(runner, mock_config, mock_client):
    """Online show saves task detail to cache for future offline use."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Task 1",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1", "id": "f1"},
            "list": {"name": "l1", "id": "l1"},
        }
        mock_client.get_task_comments.return_value = [
            {"user": {"username": "alice"}, "text": "a note", "date": None}
        ]
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        mock_config.save_task_detail.assert_called_once()
        saved_id, saved_data = mock_config.save_task_detail.call_args[0]
        assert saved_id == "t1"
        assert saved_data["task"]["name"] == "Task 1"
        assert len(saved_data["comments"]) == 1


def test_show_task_displays_tags(runner, mock_config, mock_client):
    """cupt show prints task tags when present."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Task 1",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1"},
            "list": {"name": "l1"},
            "tags": [{"name": "urgent"}, {"name": "billing"}],
        }
        mock_client.get_task_comments.return_value = []
        result = runner.invoke(show_task_cmd, ["t1"])
        assert result.exit_code == 0
        assert "Tags:" in result.output
        assert "urgent" in result.output
        assert "billing" in result.output


def test_list_tasks_offline_tag_filter(runner, mock_config, mock_client):
    """--tag filter applies in offline mode too."""
    mock_config.load_task_cache.return_value = {
        "tasks": [
            {
                "id": "t1",
                "name": "Tagged Task",
                "status": {"status": "open"},
                "tags": [{"name": "urgent"}],
            },
            {
                "id": "t2",
                "name": "Untagged Task",
                "status": {"status": "open"},
                "tags": [],
            },
        ],
        "timestamp": time.time(),
    }
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(list_tasks_cmd, ["--offline", "--tag", "urgent"])
        assert result.exit_code == 0
        assert "Tagged Task" in result.output
        assert "Untagged Task" not in result.output


def test_show_task_json_output(runner, mock_config, mock_client):
    """show --json bundles task + parent + comments as JSON."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "name": "Task 1",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1"},
            "list": {"name": "l1"},
        }
        mock_client.get_task_comments.return_value = [
            {"user": {"username": "alice"}, "text": "a note"}
        ]
        result = runner.invoke(show_task_cmd, ["t1", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["task"]["id"] == "t1"
        assert payload["parent"] is None
        assert payload["comments"][0]["text"] == "a note"


def test_show_task_offline_from_detail_cache(runner, mock_config, mock_client):
    """--offline reads from task detail cache without any API calls."""
    mock_config.load_task_detail.return_value = {
        "task": {
            "id": "t1",
            "name": "Cached Task",
            "status": {"status": "open"},
            "space": {"id": "s1"},
            "folder": {"name": "f1", "id": "f1"},
            "list": {"name": "l1", "id": "l1"},
        },
        "parent": None,
        "comments": [],
        "cached_at": time.time(),
    }
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(show_task_cmd, ["t1", "--offline"])
        assert result.exit_code == 0
        assert "Cached Task" in result.output
        assert "Offline mode" in result.output
        mock_client.get_task.assert_not_called()


def test_show_task_offline_fallback_to_list_cache(runner, mock_config, mock_client):
    """--offline falls back to list cache with a partial-data warning."""
    mock_config.load_task_detail.return_value = None
    mock_config.load_task_cache.return_value = {
        "tasks": [{"id": "t1", "name": "List Task", "status": {"status": "open"}}],
        "timestamp": time.time(),
    }
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(show_task_cmd, ["t1", "--offline"])
        assert result.exit_code == 0
        assert "List Task" in result.output
        assert "Partial offline data" in result.output
        mock_client.get_task.assert_not_called()


def test_show_task_offline_no_cache(runner, mock_config, mock_client):
    """--offline with no cache at all shows a helpful error."""
    mock_config.load_task_detail.return_value = None
    mock_config.load_task_cache.return_value = None
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(show_task_cmd, ["t1", "--offline"])
        assert result.exit_code == 0
        assert "not in offline cache" in result.output
        mock_client.get_task.assert_not_called()


# ---------------------------------------------------------------------------
# prefetch
# ---------------------------------------------------------------------------


def test_prefetch_cmd_caches_tasks(runner, mock_config, mock_client):
    """prefetch fetches details for all tasks and saves them."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": "t1",
                "name": "Task 1",
                "status": {"status": "open", "type": "open"},
            },
            {
                "id": "t2",
                "name": "Task 2",
                "status": {"status": "open", "type": "open"},
            },
        ]
        mock_client.get_task.side_effect = lambda tid: {
            "id": tid,
            "name": f"Full {tid}",
        }
        mock_client.get_task_comments.return_value = []

        result = runner.invoke(prefetch_cmd, [])
        assert result.exit_code == 0
        assert "Cached 2/2" in result.output
        assert mock_config.save_task_detail.call_count == 2


def test_prefetch_cmd_respects_limit(runner, mock_config, mock_client):
    """--limit restricts how many tasks are prefetched."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = [
            {
                "id": f"t{i}",
                "name": f"Task {i}",
                "status": {"status": "open", "type": "open"},
            }
            for i in range(5)
        ]
        mock_client.get_task.side_effect = lambda tid: {
            "id": tid,
            "name": f"Full {tid}",
        }
        mock_client.get_task_comments.return_value = []

        result = runner.invoke(prefetch_cmd, ["-n", "2"])
        assert result.exit_code == 0
        assert mock_config.save_task_detail.call_count == 2


def test_prefetch_cmd_no_tasks(runner, mock_config, mock_client):
    """prefetch with an empty task list prints a warning."""
    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.get_team_tasks.return_value = []
        result = runner.invoke(prefetch_cmd, [])
        assert result.exit_code == 0
        assert "No tasks found" in result.output
        mock_config.save_task_detail.assert_not_called()
