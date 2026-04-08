from unittest.mock import patch
from cupt.notes import add_note, list_notes
from click.testing import CliRunner

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


def test_notes_auth_error():
    runner = CliRunner()
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        result = runner.invoke(add_note, ["abc", "note"])
        assert "Not authenticated" in result.output
