from unittest.mock import MagicMock, patch

from cupt.attachments import attach_group


def _ctx(mock_config, mock_client, team_id="team1"):
    return (mock_config, mock_client, team_id)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_attach_list(runner, mock_config, mock_client):
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "attachments": [
                {"id": "a1", "title": "report.pdf", "size": 1024 * 50},
                {"id": "a2", "title": "photo.jpg", "size": 1024 * 1024 * 2},
            ],
        }
        result = runner.invoke(attach_group, ["list", "t1"])
        assert result.exit_code == 0
        assert "report.pdf" in result.output
        assert "photo.jpg" in result.output


def test_attach_list_empty(runner, mock_config, mock_client):
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_task.return_value = {"id": "t1", "attachments": []}
        result = runner.invoke(attach_group, ["list", "t1"])
        assert result.exit_code == 0
        assert "No attachments" in result.output


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_attach_get_by_index(runner, mock_config, mock_client, tmp_path):
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "attachments": [
                {"id": "a1", "title": "report.pdf", "url": "https://s3/report.pdf"},
            ],
        }
        fake_response = MagicMock()
        fake_response.iter_content.return_value = [b"PDF-CONTENT"]
        fake_response.raise_for_status.return_value = None
        out_path = tmp_path / "downloaded.pdf"
        with patch("cupt.attachments.requests.get", return_value=fake_response) as g:
            result = runner.invoke(
                attach_group, ["get", "t1", "1", "-o", str(out_path)]
            )
            assert result.exit_code == 0
            # No Authorization header to the pre-signed S3 URL.
            _, kwargs = g.call_args
            assert "headers" not in kwargs or "Authorization" not in (
                kwargs.get("headers") or {}
            )
            assert out_path.read_bytes() == b"PDF-CONTENT"
            assert "Downloaded report.pdf" in result.output


def test_attach_get_by_substring(runner, mock_config, mock_client, tmp_path):
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "attachments": [
                {"id": "a1", "title": "quarterly-report.pdf", "url": "https://s3/r"},
                {"id": "a2", "title": "selfie.jpg", "url": "https://s3/s"},
            ],
        }
        fake_response = MagicMock()
        fake_response.iter_content.return_value = [b"X"]
        fake_response.raise_for_status.return_value = None
        out_path = tmp_path / "out.pdf"
        with patch("cupt.attachments.requests.get", return_value=fake_response):
            result = runner.invoke(
                attach_group, ["get", "t1", "quarterly", "-o", str(out_path)]
            )
            assert result.exit_code == 0
            assert "quarterly-report.pdf" in result.output


def test_attach_get_ambiguous(runner, mock_config, mock_client):
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "attachments": [
                {"id": "a1", "title": "report-v1.pdf", "url": "https://s3/1"},
                {"id": "a2", "title": "report-v2.pdf", "url": "https://s3/2"},
            ],
        }
        result = runner.invoke(attach_group, ["get", "t1", "report"])
        assert result.exit_code != 0
        assert "matches 2 attachments" in result.output


def test_attach_get_no_match(runner, mock_config, mock_client):
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.get_task.return_value = {
            "id": "t1",
            "attachments": [
                {"id": "a1", "title": "report.pdf", "url": "https://s3/r"},
            ],
        }
        result = runner.invoke(attach_group, ["get", "t1", "nonexistent"])
        assert result.exit_code == 0
        assert "No attachment matches" in result.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


def test_attach_add(runner, mock_config, mock_client, tmp_path):
    upload_file = tmp_path / "hello.txt"
    upload_file.write_text("hello world")
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.upload_task_attachment.return_value = {
            "id": "a1",
            "title": "hello.txt",
        }
        result = runner.invoke(attach_group, ["add", "t1", str(upload_file)])
        assert result.exit_code == 0
        assert "Attached 'hello.txt'" in result.output
        mock_client.upload_task_attachment.assert_called_once_with(
            "t1", str(upload_file), None
        )


def test_attach_add_error(runner, mock_config, mock_client, tmp_path):
    upload_file = tmp_path / "hello.txt"
    upload_file.write_text("hi")
    with patch(
        "cupt.attachments.get_client_context",
        return_value=_ctx(mock_config, mock_client),
    ):
        mock_client.upload_task_attachment.side_effect = Exception("boom")
        result = runner.invoke(attach_group, ["add", "t1", str(upload_file)])
        assert result.exit_code == 0
        assert "Failed to upload attachment" in result.output
