import json
from pathlib import Path
from unittest.mock import patch

from cupt.api import ClickUpClient
from cupt.notes import list_notes
from cupt.tasks import context_cmd, show_task_cmd, statuses_cmd
from cupt.utils import format_comment_author, format_comment_text


def _ctx(mock_config, mock_client, workspace_id="workspace_fixture_1"):
    return (mock_config, mock_client, workspace_id)


def _fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "clickup"


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def test_sanitized_clickup_fixtures_do_not_contain_contact_data():
    for path in _fixture_dir().glob("*.json"):
        data = json.loads(path.read_text())
        strings = list(_walk_strings(data))
        assert all("@" not in value for value in strings), path
        assert all("http://" not in value.lower() for value in strings), path
        assert all("https://" not in value.lower() for value in strings), path


def test_comment_fixture_preserves_clickup_comment_shapes(fixture_json):
    comments = fixture_json("clickup/task_comments_response.json")["comments"]

    assert comments[0]["comment_text"] == (
        "First sanitized comment line\nSecond sanitized comment line"
    )
    assert format_comment_text(comments[0]) == (
        "First sanitized comment line\nSecond sanitized comment line"
    )
    assert format_comment_text(comments[1]) == (
        "Rich text fallback comment\nRendered from rich segments"
    )
    assert format_comment_author(comments[0]) == "Example User"


def test_api_client_extracts_comments_from_clickup_fixture(fixture_json):
    response_payload = fixture_json("clickup/task_comments_response.json")

    with patch("requests.Session") as session_cls:
        session = session_cls.return_value
        session.get.return_value.status_code = 200
        session.get.return_value.json.return_value = response_payload

        client = ClickUpClient("token")
        comments = client.get_task_comments("task_fixture_1")

    assert comments == response_payload["comments"]
    assert comments[0]["comment_text"].startswith("First sanitized")


def test_notes_command_renders_sanitized_clickup_comments(
    runner, mock_config, mock_client, fixture_json
):
    comments = fixture_json("clickup/task_comments_response.json")["comments"]
    mock_client.get_task_comments.return_value = comments

    with patch(
        "cupt.notes.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(list_notes, ["task_fixture_1"])

    assert result.exit_code == 0
    assert "First sanitized comment line" in result.output
    assert "Rich text fallback comment" in result.output


def test_context_command_renders_sanitized_clickup_payloads(
    runner, mock_config, mock_client, fixture_json
):
    task = fixture_json("clickup/task_detail_response.json")
    comments = fixture_json("clickup/task_comments_response.json")["comments"]
    children = fixture_json("clickup/task_children_response.json")["tasks"]
    mock_client.get_task.return_value = task
    mock_client.get_task_comments.return_value = comments
    mock_client.get_task_children.return_value = children

    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(context_cmd, ["task_fixture_1"])

    assert result.exit_code == 0
    assert "Sample Task With Sanitized Data" in result.output
    assert "[Example User]: First sanitized comment line" in result.output
    assert "Sample Subtask" in result.output


def test_show_notes_command_renders_sanitized_clickup_payloads(
    runner, mock_config, mock_client, fixture_json
):
    task = fixture_json("clickup/task_detail_response.json")
    comments = fixture_json("clickup/task_comments_response.json")["comments"]
    mock_client.get_task.return_value = task
    mock_client.get_task_comments.return_value = comments

    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(show_task_cmd, ["task_fixture_1", "--notes"])

    assert result.exit_code == 0
    assert "Sample Task With Sanitized Data" in result.output
    assert "First sanitized comment line" in result.output
    assert "Rich text fallback comment" in result.output


def test_statuses_command_renders_sanitized_clickup_status_payload(
    runner, mock_config, mock_client, fixture_json
):
    task = fixture_json("clickup/task_detail_response.json")
    statuses = fixture_json("clickup/list_statuses_response.json")["statuses"]
    mock_client.get_task.return_value = task
    mock_client.get_list_statuses.return_value = statuses

    with patch(
        "cupt.tasks.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(statuses_cmd, ["task_fixture_1", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["list_id"] == "list_fixture_1"
    assert payload["target"] == "complete"
    assert payload["statuses"] == statuses
