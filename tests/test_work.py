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
