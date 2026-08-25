"""Tests for cupt work focus mode."""

import json
from unittest.mock import patch

from cupt.work import work_cmd


def _ctx(config, client):
    return config, client, "workspace1"


def _task(task_id="t1", name="Task 1"):
    return {"id": task_id, "name": name, "status": {"status": "open", "type": "open"}}


def test_work_json_prints_queue(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [_task()]
    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(work_cmd, ["--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert payload["tasks"][0]["id"] == "t1"


def test_work_non_interactive_refuses_prompt(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [_task()]
    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(work_cmd, env={"CUPT_INTERACTIVE": "0"})

    assert result.exit_code == 0
    assert "interactive-only" in result.output


def test_work_done_completes_task(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [_task()]
    mock_client.get_task.return_value = {**_task(), "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
    mock_client.get_running_timer.return_value = {"id": "timer1"}

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="d\n")

    assert result.exit_code == 0
    assert "marked as 'Done'" in result.output
    mock_client.update_task.assert_called_once_with("t1", {"status": "Done"})


# ---------------------------------------------------------------------------
# timer / active-task agreement
#
# `get_running_timer` is workspace-scoped, so focus mode used to skip starting
# a timer whenever *any* timer was running — leaving the active pointer on the
# new task while the minutes kept landing on the old one.
# ---------------------------------------------------------------------------


def _timer_for(task_id):
    """A running time entry in the nested shape ClickUp returns."""
    return {"id": "timer1", "task": {"id": task_id, "name": f"Task {task_id}"}}


def test_running_timer_task_id_accepts_both_payload_shapes():
    from cupt.work import _running_timer_task_id

    assert _running_timer_task_id({"task": {"id": "t1"}}) == "t1"
    assert _running_timer_task_id({"task_id": "t1"}) == "t1"
    assert _running_timer_task_id({"id": "timer1"}) is None
    assert _running_timer_task_id(None) is None


def test_work_moves_timer_to_the_newly_active_task(runner, mock_config, mock_client):
    """Regression: choosing [w] twice must not leave the timer on task one."""
    mock_client.get_workspace_tasks.return_value = [_task("t1"), _task("t2", "Task 2")]
    mock_client.get_task.side_effect = lambda tid: {**_task(tid), "list": {"id": "l1"}}

    running = {"entry": None}
    mock_client.get_running_timer.side_effect = lambda ws: running["entry"]
    mock_client.start_timer.side_effect = lambda ws, tid: running.__setitem__(
        "entry", _timer_for(tid)
    )
    mock_client.stop_timer.side_effect = lambda ws: running.__setitem__("entry", None)

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="w\nw\n")

    assert result.exit_code == 0
    assert running["entry"]["task"]["id"] == "t2"
    mock_client.stop_timer.assert_called_once_with("workspace1")
    assert "Stopped the timer on t1" in result.output


def test_work_leaves_an_already_correct_timer_alone(runner, mock_config, mock_client):
    """[w] on the task already being timed must not churn stop/start."""
    mock_client.get_workspace_tasks.return_value = [_task("t1")]
    mock_client.get_task.return_value = {**_task("t1"), "list": {"id": "l1"}}
    mock_client.get_running_timer.return_value = _timer_for("t1")

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="w\n")

    assert result.exit_code == 0
    mock_client.stop_timer.assert_not_called()
    mock_client.start_timer.assert_not_called()


def test_work_starts_a_timer_when_none_is_running(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [_task("t1")]
    mock_client.get_task.return_value = {**_task("t1"), "list": {"id": "l1"}}
    mock_client.get_running_timer.return_value = None

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="w\n")

    assert result.exit_code == 0
    mock_client.start_timer.assert_called_once_with("workspace1", "t1")
    mock_client.stop_timer.assert_not_called()


def test_work_timer_failure_warns_but_still_sets_active(
    runner, mock_config, mock_client
):
    mock_client.get_workspace_tasks.return_value = [_task("t1")]
    mock_client.get_task.return_value = {**_task("t1"), "list": {"id": "l1"}}
    mock_client.get_running_timer.return_value = None
    mock_client.start_timer.side_effect = RuntimeError("boom")

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="w\n")

    assert result.exit_code == 0
    assert "Could not start timer" in result.output
    assert "Active: t1" in result.output


def test_work_done_does_not_stop_another_tasks_timer(runner, mock_config, mock_client):
    """[d] on task two must leave a timer that belongs to task one running."""
    mock_client.get_workspace_tasks.return_value = [_task("t2", "Task 2")]
    mock_client.get_task.return_value = {**_task("t2"), "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
    mock_client.get_running_timer.return_value = _timer_for("t1")

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="d\n")

    assert result.exit_code == 0
    assert "marked as 'Done'" in result.output
    mock_client.stop_timer.assert_not_called()


def test_work_done_stops_this_tasks_timer(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [_task("t1")]
    mock_client.get_task.return_value = {**_task("t1"), "list": {"id": "l1"}}
    mock_client.get_list_statuses.return_value = [{"status": "Done", "type": "closed"}]
    mock_client.get_running_timer.return_value = _timer_for("t1")

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="d\n")

    assert result.exit_code == 0
    mock_client.stop_timer.assert_called_once_with("workspace1")


def test_work_quit_stops_the_session(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = [_task("t1"), _task("t2", "Task 2")]
    mock_client.get_task.side_effect = lambda tid: {**_task(tid), "list": {"id": "l1"}}

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="q\n")

    assert result.exit_code == 0
    assert "Work session ended." in result.output
    assert "Task 2/2" not in result.output


def test_work_rejects_an_unknown_choice_then_accepts_skip(
    runner, mock_config, mock_client
):
    mock_client.get_workspace_tasks.return_value = [_task("t1")]
    mock_client.get_task.return_value = {**_task("t1"), "list": {"id": "l1"}}

    with patch(
        "cupt.work.get_client_context", return_value=_ctx(mock_config, mock_client)
    ), patch("cupt.work.is_interactive", return_value=True):
        result = runner.invoke(work_cmd, input="z\ns\n")

    assert result.exit_code == 0
    assert "Choose w, s, d, or q." in result.output
    assert "Skipped: t1" in result.output
