from unittest.mock import MagicMock, patch

import pytest

from cupt.services.field_service import display_value
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


# ---------------------------------------------------------------------------
# field_value / filter_by_fields / filter_by_list_names / sort_by_field
# ---------------------------------------------------------------------------


def _drop_down_task(name="Repo", value=1, options=None, field_name=None):
    return {
        "custom_fields": [
            {
                "name": field_name or name,
                "type": "drop_down",
                "value": value,
                "type_config": {
                    "options": options
                    or [
                        {"id": "opt-a", "orderindex": 0, "name": "backend"},
                        {"id": "opt-b", "orderindex": 1, "name": "astro-site"},
                    ]
                },
            }
        ]
    }


def test_field_value_drop_down_resolves_to_name_not_uuid(service):
    """A drop_down's raw `value` (an orderindex or option id) must never
    leak to the caller — it must resolve to the option's name."""
    task = _drop_down_task(value=1)
    assert TaskService.field_value(task, "Repo") == "astro-site"


def test_field_value_drop_down_resolves_by_option_id(service):
    task = _drop_down_task(value="opt-a")
    assert TaskService.field_value(task, "Repo") == "backend"


def test_field_value_drop_down_uses_label_when_no_name(service):
    """Some field types use `label` instead of `name` on their options."""
    task = _drop_down_task(
        value=0, options=[{"id": "opt-a", "orderindex": 0, "label": "Nothing"}]
    )
    assert TaskService.field_value(task, "Repo") == "Nothing"

    assert TaskService.field_value(task, "repo") == "Nothing"
    assert TaskService.field_value(task, "  Repo  ") == "Nothing"


def test_field_value_labels_resolves_to_list_of_names(service):
    task = {
        "custom_fields": [
            {
                "name": "Tags",
                "type": "labels",
                "value": ["l1", "l2"],
                "type_config": {
                    "options": [
                        {"id": "l1", "name": "urgent"},
                        {"id": "l2", "label": "billing"},
                    ]
                },
            }
        ]
    }
    assert TaskService.field_value(task, "Tags") == ["urgent", "billing"]


def test_field_value_unset_returns_none(service):
    task = {"custom_fields": [{"name": "Size", "type": "number", "value": None}]}
    assert TaskService.field_value(task, "Size") is None


def test_field_value_missing_field_returns_none(service):
    assert TaskService.field_value({"custom_fields": []}, "Size") is None
    assert TaskService.field_value({}, "Size") is None


def test_field_value_plain_type_returned_as_is(service):
    task = {"custom_fields": [{"name": "Size", "type": "number", "value": 8}]}
    assert TaskService.field_value(task, "Size") == 8


def test_filter_by_fields_no_filter_returns_all(service):
    tasks = [{"id": "t1"}]
    assert TaskService.filter_by_fields(tasks, required=None) == tasks
    assert TaskService.filter_by_fields(tasks, required={}) == tasks


def test_filter_by_fields_and_semantics(service):
    """AND across distinct field names — task must match every entry."""

    def task(repo, size):
        return {
            "id": f"{repo}-{size}",
            "custom_fields": [
                {"name": "Repo", "type": "text", "value": repo},
                {"name": "Size", "type": "number", "value": size},
            ],
        }

    tasks = [task("astro-site", 3), task("astro-site", 5), task("other", 3)]
    out = TaskService.filter_by_fields(
        tasks, required={"Repo": "astro-site", "Size": "3"}
    )
    assert [t["id"] for t in out] == ["astro-site-3"]


def test_filter_by_fields_missing_field_is_dropped(service):
    tasks = [
        {"id": "t1", "custom_fields": [{"name": "Repo", "type": "text", "value": "x"}]},
        {"id": "t2", "custom_fields": []},
    ]
    out = TaskService.filter_by_fields(tasks, required={"Repo": "x"})
    assert [t["id"] for t in out] == ["t1"]


def test_filter_by_fields_matches_any_element_of_list_valued_field(service):
    task = {
        "id": "t1",
        "custom_fields": [
            {
                "name": "Tags",
                "type": "labels",
                "value": ["l1", "l2"],
                "type_config": {
                    "options": [
                        {"id": "l1", "name": "urgent"},
                        {"id": "l2", "name": "billing"},
                    ]
                },
            }
        ],
    }
    out = TaskService.filter_by_fields(tasks=[task], required={"Tags": "billing"})
    assert len(out) == 1
    out = TaskService.filter_by_fields(tasks=[task], required={"Tags": "missing"})
    assert out == []


def test_filter_by_fields_case_insensitive(service):
    task = {
        "id": "t1",
        "custom_fields": [{"name": "Repo", "type": "text", "value": "Astro-Site"}],
    }
    out = TaskService.filter_by_fields(tasks=[task], required={"repo": "astro-site"})
    assert len(out) == 1


def test_filter_by_list_names_no_filter_returns_all(service):
    tasks = [{"id": "t1"}]
    assert TaskService.filter_by_list_names(tasks, required=None) == tasks
    assert TaskService.filter_by_list_names(tasks, required=[]) == tasks


def test_filter_by_list_names_case_insensitive_or_semantics(service):
    tasks = [
        {"id": "t1", "list": {"name": "Website"}},
        {"id": "t2", "list": {"name": "Marketing"}},
        {"id": "t3", "list": {"name": "backlog"}},
    ]
    out = TaskService.filter_by_list_names(tasks, required=["website", "Backlog"])
    assert {t["id"] for t in out} == {"t1", "t3"}


def test_filter_by_list_names_missing_list_dropped(service):
    tasks = [{"id": "t1"}, {"id": "t2", "list": {"name": "Website"}}]
    out = TaskService.filter_by_list_names(tasks, required=["Website"])
    assert [t["id"] for t in out] == ["t2"]


def _sized_task(task_id, size_value=None):
    return {
        "id": task_id,
        "custom_fields": [{"name": "Size", "type": "number", "value": size_value}],
    }


def test_sort_by_field_ascending_numeric(service):
    tasks = [_sized_task("big", 8), _sized_task("small", 1), _sized_task("mid", 3)]
    out = TaskService.sort_by_field(tasks, "Size")
    assert [t["id"] for t in out] == ["small", "mid", "big"]


def test_sort_by_field_missing_and_non_numeric_sort_last_stably(service):
    """Tasks with a missing or non-numeric value sort after all numeric
    ones, retaining their relative input order (stable sort)."""
    tasks = [
        _sized_task("no_field"),  # value None -> field_value returns None
        _sized_task("has_value", 2),
        {
            "id": "non_numeric",
            "custom_fields": [{"name": "Size", "type": "text", "value": "large"}],
        },
        _sized_task("also_missing"),
    ]
    out = TaskService.sort_by_field(tasks, "Size")
    assert [t["id"] for t in out] == [
        "has_value",
        "no_field",
        "non_numeric",
        "also_missing",
    ]


def test_sort_by_field_does_not_mutate_input(service):
    tasks = [_sized_task("big", 8), _sized_task("small", 1)]
    original_order = [t["id"] for t in tasks]
    TaskService.sort_by_field(tasks, "Size")
    assert [t["id"] for t in tasks] == original_order


# ---------------------------------------------------------------------------
# statuses[] / deep_scan
# ---------------------------------------------------------------------------


def test_list_tasks_passes_statuses_to_api(service, mock_client):
    """statuses= argument is forwarded as ClickUp's statuses[] filter
    (server-side, supported natively unlike tags/teams)."""
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1", statuses=["to do", "in progress"])
    filters = mock_client.get_workspace_tasks.call_args[0][1]
    assert filters["statuses[]"] == ["to do", "in progress"]


def test_list_tasks_omits_statuses_when_empty(service, mock_client):
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1")
    filters = mock_client.get_workspace_tasks.call_args[0][1]
    assert "statuses[]" not in filters


def test_list_tasks_deep_scan_suppresses_early_exit(service, mock_client):
    """deep_scan=True has the same pagination effect as teams_filter=True,
    for callers whose client-side filter isn't team-based."""
    page_full = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100)]
    page_short = [{"id": "t_last", "status": {"type": "open"}}]
    mock_client.get_workspace_tasks.side_effect = [page_full, page_full, page_short]

    tasks = service.list_tasks("ws1", mine=False, deep_scan=True)

    assert mock_client.get_workspace_tasks.call_count == 3
    assert len(tasks) == 201


def test_list_tasks_deep_scan_false_keeps_early_exit(service, mock_client):
    page_full = [{"id": f"t{i}", "status": {"type": "open"}} for i in range(100)]
    mock_client.get_workspace_tasks.side_effect = [page_full, page_full]

    tasks = service.list_tasks("ws1", mine=False)

    assert mock_client.get_workspace_tasks.call_count == 1
    assert len(tasks) == 100


# ---------------------------------------------------------------------------
# custom_items[] (task type filter)
# ---------------------------------------------------------------------------


def test_list_tasks_passes_custom_item_ids_to_api(service, mock_client):
    """custom_item_ids= is forwarded as ClickUp's server-side custom_items[]
    filter (OR semantics), like statuses — not client-side."""
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1", custom_item_ids=[1002, 3])
    filters = mock_client.get_workspace_tasks.call_args[0][1]
    assert filters["custom_items[]"] == [1002, 3]


def test_list_tasks_custom_item_ids_zero_is_not_dropped(service, mock_client):
    """0 (the default task type) is a legitimate id and must survive an
    `is not None` check, not a truthiness check."""
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1", custom_item_ids=[0])
    filters = mock_client.get_workspace_tasks.call_args[0][1]
    assert filters["custom_items[]"] == [0]


def test_list_tasks_omits_custom_item_ids_when_none(service, mock_client):
    mock_client.get_workspace_tasks.return_value = []
    service.list_tasks("team1")
    filters = mock_client.get_workspace_tasks.call_args[0][1]
    assert "custom_items[]" not in filters


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


def test_field_value_agrees_with_field_list_on_an_unresolvable_option():
    """Filtering and display share one implementation, so a value matching no
    current option is None on both sides — a filter declines to match rather
    than matching on an id the user never typed."""
    field = {
        "id": "f1",
        "name": "Release group",
        "type": "drop_down",
        "type_config": {"options": [{"id": "opt-1", "name": "Alpha"}]},
        "value": "uuid-of-a-deleted-option",
    }
    task = {"id": "t1", "custom_fields": [field]}

    assert TaskService.field_value(task, "Release group") is None
    assert display_value(field) is None
    assert TaskService.filter_by_fields([task], {"Release group": "Alpha"}) == []
