import pytest
from unittest.mock import MagicMock, patch
from cupt.notes import add_note, list_notes

@pytest.fixture
def mock_config():
    with patch('cupt.notes.ConfigManager') as mock:
        instance = mock.return_value
        instance.is_authenticated.return_value = True
        instance.get.return_value = "token"
        yield instance

@pytest.fixture
def mock_client():
    with patch('cupt.notes.ClickUpClient') as mock:
        yield mock.return_value

def test_add_note(mock_config, mock_client):
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(add_note, ["abc", "Test Note"])
    
    assert result.exit_code == 0
    mock_client.add_task_comment.assert_called_with("abc", "Test Note")

def test_list_notes(mock_config, mock_client):
    mock_client.get_task_comments.return_value = [
        {"user": {"username": "test"}, "text": "Comment 1", "date": 12345}
    ]
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(list_notes, ["abc"])
    
    assert result.exit_code == 0
    assert "Comment 1" in result.output
