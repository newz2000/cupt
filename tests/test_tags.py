from unittest.mock import patch

from cupt.tags import tag_group


def _ctx(mock_config, mock_client, team_id="team1"):
    return (mock_config, mock_client, team_id)


def test_tag_add(runner, mock_config, mock_client):
    with patch(
        "cupt.tags.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(tag_group, ["add", "t1", "urgent"])
        assert result.exit_code == 0
        assert "Tagged t1 with 'urgent'" in result.output
        mock_client.add_task_tag.assert_called_once_with("t1", "urgent")


def test_tag_remove(runner, mock_config, mock_client):
    with patch(
        "cupt.tags.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        result = runner.invoke(tag_group, ["remove", "t1", "urgent"])
        assert result.exit_code == 0
        assert "Removed 'urgent' from t1" in result.output
        mock_client.remove_task_tag.assert_called_once_with("t1", "urgent")


def test_tag_add_api_error(runner, mock_config, mock_client):
    with patch(
        "cupt.tags.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.add_task_tag.side_effect = Exception("API Error")
        result = runner.invoke(tag_group, ["add", "t1", "urgent"])
        assert result.exit_code == 0
        assert "Failed to add tag" in result.output


def test_tag_remove_api_error(runner, mock_config, mock_client):
    with patch(
        "cupt.tags.get_client_context", return_value=_ctx(mock_config, mock_client)
    ):
        mock_client.remove_task_tag.side_effect = Exception("API Error")
        result = runner.invoke(tag_group, ["remove", "t1", "urgent"])
        assert result.exit_code == 0
        assert "Failed to remove tag" in result.output
