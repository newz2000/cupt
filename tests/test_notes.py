import json
from unittest.mock import patch

from click.testing import CliRunner

from cupt.notes import add_note, list_notes

_MODULE = "cupt.notes.get_client_context"


def _ctx(mock_config, mock_client):
    return (mock_config, mock_client, None)  # notes don't use team_id


def test_add_note(mock_config, mock_client):
    runner = CliRunner()
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        result = runner.invoke(add_note, ["abc", "Test Note"])
        assert result.exit_code == 0
        mock_client.add_task_comment.assert_called_with("abc", "Test Note")


def test_list_notes(mock_config, mock_client):
    runner = CliRunner()
    mock_client.get_task_comments.return_value = [
        {"user": {"username": "test"}, "text": "Comment 1", "date": 12345}
    ]
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        result = runner.invoke(list_notes, ["abc"])
        assert result.exit_code == 0
        assert "Comment 1" in result.output


def test_list_notes_displays_clickup_comment_text(mock_config, mock_client):
    runner = CliRunner()
    mock_client.get_task_comments.return_value = [
        {
            "user": {"username": "test"},
            "comment_text": "Real ClickUp note",
            "date": 12345,
        }
    ]
    with patch(_MODULE, return_value=_ctx(mock_config, mock_client)):
        result = runner.invoke(list_notes, ["abc"])
        assert result.exit_code == 0
        assert "Real ClickUp note" in result.output


def test_notes_auth_error():
    runner = CliRunner()
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        result = runner.invoke(add_note, ["abc", "note"])
        assert "Not authenticated" in result.output


def test_notes_json_emits_an_array(runner, mock_config, mock_client):
    mock_client.get_task_comments.return_value = [
        {"id": "c1", "comment_text": "hello", "date": "1700000000000"}
    ]
    with patch(
        "cupt.notes.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(list_notes, ["868abc", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task_id"] == "868abc"
    assert payload["notes"][0]["comment_text"] == "hello"


def test_notes_json_is_empty_array_not_a_warning(runner, mock_config, mock_client):
    """Scripts branch on the array; an empty result is success, not a warning."""
    mock_client.get_task_comments.return_value = []
    with patch(
        "cupt.notes.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(list_notes, ["868abc", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["notes"] == []
