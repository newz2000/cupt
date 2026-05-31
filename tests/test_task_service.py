from unittest.mock import MagicMock, patch

import pytest

from cupt.services.task_service import TaskService


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def service(mock_client):
    return TaskService(mock_client)


def test_get_filters_base(service):
    filters = service.get_filters()
    assert filters["subtasks"] == "true"
    assert filters["include_subtasks"] == "true"


def test_list_tasks_filtering(service, mock_client):
    mock_client.get_workspace_tasks.return_value = [
        {"id": "t1", "status": {"type": "open"}},
        {"id": "t2", "status": {"type": "closed"}},
    ]

    # Test open only
    tasks = service.list_tasks("team1", include_closed=False)
    assert len(tasks) == 1
    assert tasks[0]["id"] == "t1"

    # Test include closed
    tasks = service.list_tasks("team1", include_closed=True)
    assert len(tasks) == 2


def test_list_tasks_teams_filter_suppresses_early_exit(service, mock_client):
    """When teams_filter=True, the 100-result early-exit is suppressed so
    client-side team matching sees later pages. Regression for the silent
    truncation that motivated 0.7.1."""
    # Three pages: 100 open tasks each. Without teams_filter, current
    # behavior stops after page 0 (cum >= 100). With teams_filter we
    # must keep walking until pages are short or max_pages is hit.
    page_full = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100)]
    page_short = [{"id": "t_last", "status": {"type": "open"}}]
    mock_client.get_workspace_tasks.side_effect = [
        page_full,
        page_full,
        page_short,
    ]

    tasks = service.list_tasks("ws1", mine=False, teams_filter=True)

    # Walked all three pages; would have stopped at 1 without the flag.
    assert mock_client.get_workspace_tasks.call_count == 3
    assert service.last_pages_walked == 3
    assert len(tasks) == 201


def test_list_tasks_no_teams_filter_keeps_early_exit(service, mock_client):
    """The early-exit is preserved for the default (non-team) path so
    plain `cupt list` doesn't suddenly become 5x more expensive."""
    page_full = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100)]
    mock_client.get_workspace_tasks.side_effect = [page_full, page_full]

    tasks = service.list_tasks("ws1", mine=False)  # teams_filter defaults to False

    assert mock_client.get_workspace_tasks.call_count == 1
    assert service.last_pages_walked == 1
    assert len(tasks) == 100


def test_list_tasks_teams_filter_bumps_all_page_cap(service, mock_client):
    """--all + --team gets max_pages=10 instead of the default 5.

    Verified by handing the service 11 full pages: without the bump it
    stops at 5; with the bump it walks 10 before hitting the cap.
    """
    page_full = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100)]
    mock_client.get_workspace_tasks.side_effect = [page_full] * 11

    service.list_tasks("ws1", mine=False, teams_filter=True)
    assert mock_client.get_workspace_tasks.call_count == 10
    assert service.last_pages_walked == 10


def test_list_tasks_records_pages_walked(service, mock_client):
    """`last_pages_walked` is the per-call instrumentation the CLI uses
    for the footer. Must reflect *this* call, not a previous one."""
    mock_client.get_workspace_tasks.side_effect = [
        [{"id": "t1", "status": {"type": "open"}}],  # short page → stop
    ]
    service.list_tasks("ws1")
    assert service.last_pages_walked == 1

    mock_client.get_workspace_tasks.reset_mock()
    page = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100)]
    mock_client.get_workspace_tasks.side_effect = [page, page[:50]]
    service.list_tasks("ws1", teams_filter=True)
    assert service.last_pages_walked == 2


def test_list_tasks_passes_tags_to_api(service, mock_client):
    """tags= argument is forwarded as ClickUp's tags[] filter (server-side OR)."""
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1", tags=["urgent", "billing"])
    _, kwargs = mock_client.get_workspace_tasks.call_args
    # filters arg is positional second
    call_args = mock_client.get_workspace_tasks.call_args[0]
    filters = call_args[1]
    assert filters["tags[]"] == ["urgent", "billing"]


def test_list_tasks_omits_tags_when_empty(service, mock_client):
    """No tags arg → no tags[] in the filter payload."""
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1")
    filters = mock_client.get_workspace_tasks.call_args[0][1]
    assert "tags[]" not in filters


def test_filter_by_teams_no_filter_returns_all(service):
    tasks = [{"id": "t1", "group_assignees": [{"id": "g1", "name": "MattTech"}]}]
    assert TaskService.filter_by_teams(tasks, required=None) == tasks
    assert TaskService.filter_by_teams(tasks, required=[]) == tasks


def test_filter_by_teams_matches_by_name(service):
    tasks = [
        {"id": "t1", "group_assignees": [{"id": "g1", "name": "MattTech"}]},
        {"id": "t2", "group_assignees": [{"id": "g2", "name": "AI Agent"}]},
        {"id": "t3", "group_assignees": []},
        {"id": "t4"},
    ]
    out = TaskService.filter_by_teams(tasks, required=["matttech"])
    assert [t["id"] for t in out] == ["t1"]


def test_filter_by_teams_matches_by_id(service):
    tasks = [
        {"id": "t1", "group_assignees": [{"id": "g1", "name": "MattTech"}]},
        {"id": "t2", "group_assignees": [{"id": "g2", "name": "AI Agent"}]},
    ]
    out = TaskService.filter_by_teams(tasks, required=["g2"])
    assert [t["id"] for t in out] == ["t2"]


def test_filter_by_teams_or_semantics(service):
    """Multiple required groups → OR (task kept if it matches any)."""
    tasks = [
        {"id": "t1", "group_assignees": [{"id": "g1", "name": "MattTech"}]},
        {"id": "t2", "group_assignees": [{"id": "g2", "name": "AI Agent"}]},
        {"id": "t3", "group_assignees": [{"id": "g3", "name": "Other"}]},
    ]
    out = TaskService.filter_by_teams(tasks, required=["MattTech", "AI Agent"])
    assert {t["id"] for t in out} == {"t1", "t2"}


def test_resolve_parent_names(service, mock_client):
    tasks = [{"id": "s1", "parent": "p1"}]
    mock_client.get_tasks_by_ids.return_value = [{"id": "p1", "name": "Parent Name"}]

    cache = {}
    service.resolve_parent_names("team1", tasks, cache)

    assert cache["p1"] == "Parent Name"
    mock_client.get_tasks_by_ids.assert_called_with("team1", ["p1"])


def test_get_filters_overdue(service):
    filters = service.get_filters(overdue=True)
    assert "due_date_lt" in filters
    assert filters["order_by"] == "due_date"


def test_get_filters_today(service):
    filters = service.get_filters(today=True)
    assert "due_date_gt" in filters
    assert "due_date_lt" in filters


def test_get_filters_week(service):
    filters = service.get_filters(week=True)
    assert "due_date_gt" in filters
    assert "due_date_lt" in filters


def test_list_tasks_with_user_filter(service, mock_client):
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1", user_id="user1", mine=True)
    args, _ = mock_client.get_workspace_tasks.call_args
    assert args[1]["assignees[]"] == ["user1"]


def test_list_tasks_pagination(service, mock_client):
    # Page 1: 100 tasks, half closed → 50 survive filtering; page isn't "short" so continue
    # Page 2: 20 tasks → short page, stop
    page_1 = [
        {"id": f"t{i}", "status": {"type": "open" if i < 50 else "closed"}}
        for i in range(100)
    ]
    page_2 = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100, 120)]
    mock_client.get_workspace_tasks.side_effect = [page_1, page_2]
    tasks = service.list_tasks("team1", mine=False, include_closed=False)
    assert len(tasks) == 70
    assert mock_client.get_workspace_tasks.call_count == 2


def test_resolve_parent_names_bulk_fails_individual_succeeds(service, mock_client):
    tasks = [{"id": "s1", "parent": "p1"}]
    mock_client.get_tasks_by_ids.return_value = []
    mock_client.get_task.return_value = {"id": "p1", "name": "Parent Via Individual"}
    cache = {}
    service.resolve_parent_names("team1", tasks, cache)
    assert cache["p1"] == "Parent Via Individual"
    mock_client.get_task.assert_called_once_with("p1")


def test_resolve_parent_names_both_fail(service, mock_client):
    tasks = [{"id": "s1", "parent": "p1"}]
    mock_client.get_tasks_by_ids.return_value = []
    mock_client.get_task.side_effect = Exception("Not found")
    cache = {}
    service.resolve_parent_names("team1", tasks, cache)
    assert cache["p1"] == "p1"


def test_resolve_parent_names_already_cached(service, mock_client):
    tasks = [{"id": "s1", "parent": "p1"}]
    cache = {"p1": "Already Cached"}
    service.resolve_parent_names("team1", tasks, cache)
    mock_client.get_tasks_by_ids.assert_not_called()
    mock_client.get_task.assert_not_called()


def test_get_task_context(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "parent": "p1", "name": "Task 1"}
    mock_client.get_task_comments.return_value = []
    mock_client.get_task_children.return_value = []

    ctx = service.get_task_context("t1", "team1")

    assert ctx["task"]["id"] == "t1"
    assert ctx["is_subtask"] is True
    mock_client.get_task.assert_any_call("t1")
    mock_client.get_task_comments.assert_called_with("t1")
    mock_client.get_task_children.assert_called_once()


def test_complete_task_success(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
    result = service.complete_task("t1")
    assert result == "Done"
    mock_client.update_task.assert_called_once_with("t1", {"status": "Done"})


def test_complete_task_no_list_id(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "list": {}}
    with pytest.raises(ValueError, match="Could not find list"):
        service.complete_task("t1")


def test_complete_task_fallback_to_space(service, mock_client):
    mock_client.get_task.return_value = {
        "id": "t1",
        "list": {"id": "l1"},
        "space": {"id": "s1"},
    }
    mock_client.get_list_statuses.return_value = []
    mock_client.get_space_statuses.return_value = [{"status": "Done", "type": "closed"}]
    result = service.complete_task("t1")
    assert result == "Done"


def test_complete_task_fallback_status_name(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [
        {"status": "Complete", "type": "open"}
    ]
    result = service.complete_task("t1")
    assert result == "Complete"


def test_complete_task_default_status(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [
        {"status": "In Progress", "type": "open"}
    ]
    result = service.complete_task("t1")
    assert result == "complete"


def test_complete_task_with_note(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
    service.complete_task("t1", note="Finished!")
    mock_client.add_task_comment.assert_called_once_with("t1", "Finished!")


# ---------------------------------------------------------------------------
# resolve_completion_status — pure resolution, no writes
# ---------------------------------------------------------------------------


def test_resolve_completion_status_returns_target_and_list(service, mock_client):
    """The canonical helper agents should call before marking a task done."""
    mock_client.get_task.return_value = {
        "id": "t1",
        "list": {"id": "l1", "name": "My Project"},
    }
    mock_client.get_list_statuses.return_value = [
        {"status": "to do", "type": "open"},
        {"status": "in progress", "type": "custom"},
        {"status": "Done", "type": "closed"},
    ]

    resolved = service.resolve_completion_status("t1")

    assert resolved["target"] == "Done"
    assert resolved["list_id"] == "l1"
    assert resolved["list_name"] == "My Project"
    assert len(resolved["all_statuses"]) == 3
    # CRITICAL: no write side-effect.
    mock_client.update_task.assert_not_called()
    mock_client.add_task_comment.assert_not_called()


def test_resolve_completion_status_raises_when_no_list(service, mock_client):
    mock_client.get_task.return_value = {"id": "t1", "list": {}}
    with pytest.raises(ValueError, match="Could not find list"):
        service.resolve_completion_status("t1")


def test_complete_task_resolves_per_list_not_globally(service, mock_client):
    """Multi-list regression: each list's "closed" name is honored independently.

    Captures the failure mode that motivated the smart-done work: an agent
    iterating a `cupt list` result that spans lists used to hard-code one
    status name and silently mis-mark tasks in the second list.
    """
    # Two tasks live in different lists with different "closed" names.
    list_statuses_by_id = {
        "list_A": [{"status": "Done", "type": "closed"}],
        "list_B": [{"status": "Complete", "type": "closed"}],
    }

    def _get_task(task_id):
        return {
            "t_a": {"id": "t_a", "list": {"id": "list_A", "name": "A"}},
            "t_b": {"id": "t_b", "list": {"id": "list_B", "name": "B"}},
        }[task_id]

    mock_client.get_task.side_effect = _get_task
    mock_client.get_list_statuses.side_effect = lambda lid: list_statuses_by_id[lid]

    # Marking both tasks done should resolve each list's own status name.
    assert service.complete_task("t_a") == "Done"
    assert service.complete_task("t_b") == "Complete"

    # And the writes should carry the per-list name, never a hard-coded one.
    update_calls = mock_client.update_task.call_args_list
    assert update_calls[0] == (("t_a", {"status": "Done"}),)
    assert update_calls[1] == (("t_b", {"status": "Complete"}),)
