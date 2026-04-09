from unittest.mock import MagicMock, patch

import pytest

from cupt.auth import OAuthManager
from cupt.config import ConfigManager


@pytest.fixture
def manager(tmp_path):
    config_file = tmp_path / "config.yaml"
    with patch("cupt.auth.ConfigManager", return_value=ConfigManager(config_file)):
        yield OAuthManager("client_id", "client_secret")


def test_logout(manager):
    with patch.object(manager.config, "set") as mock_set:
        manager.logout()
        # Verify both tokens are cleared
        assert mock_set.call_count >= 2


def test_refresh_tokens_success(manager):
    with patch.object(manager.config, "get", return_value="refresh_token"), patch(
        "requests.post"
    ) as mock_post:

        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
        }

        assert manager.refresh_tokens() is True
        mock_post.assert_called_once()


def test_refresh_tokens_failure(manager):
    with patch.object(manager.config, "get", return_value=None):
        assert manager.refresh_tokens() is False


def test_exchange_code_for_tokens(manager):
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "access_token": "acc123",
            "refresh_token": "ref123",
        }

        res = manager._exchange_code_for_tokens("test_code")
        assert res["access_token"] == "acc123"
        mock_post.assert_called_once()


def test_callback_handler_success(manager):
    from cupt.auth import OAuthCallbackHandler

    # Mock __init__ to avoid socket errors
    with patch("http.server.BaseHTTPRequestHandler.__init__", return_value=None):
        handler = OAuthCallbackHandler(manager)
        handler.path = "/?code=testcode"
        handler.wfile = MagicMock()

        # Mock methods called during do_GET
        with patch.object(handler, "send_response"), patch.object(
            handler, "send_header"
        ), patch.object(handler, "end_headers"):

            handler.do_GET()

            assert manager.auth_code == "testcode"
            assert manager.received is True


def test_callback_handler_error(manager):
    from cupt.auth import OAuthCallbackHandler

    with patch("http.server.BaseHTTPRequestHandler.__init__", return_value=None):
        handler = OAuthCallbackHandler(manager)
        handler.path = "/?error=access_denied"
        handler.wfile = MagicMock()

        with patch.object(handler, "send_response"), patch.object(
            handler, "send_header"
        ), patch.object(handler, "end_headers"):

            handler.do_GET()
            assert manager.received is False
            assert manager.auth_code is None


def test_callback_handler_no_code_no_error(manager):
    from cupt.auth import OAuthCallbackHandler

    with patch("http.server.BaseHTTPRequestHandler.__init__", return_value=None):
        handler = OAuthCallbackHandler(manager)
        handler.path = "/favicon.ico"
        handler.wfile = MagicMock()
        with patch.object(handler, "send_response") as mock_resp, patch.object(
            handler, "send_header"
        ), patch.object(handler, "end_headers"):
            handler.do_GET()
            mock_resp.assert_called_with(400)
            assert manager.received is False


def test_exchange_code_non_200(manager):
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 400
        mock_post.return_value.text = "Bad request"
        result = manager._exchange_code_for_tokens("bad_code")
        assert result is None


def test_exchange_code_no_access_token(manager):
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"error": "something"}
        result = manager._exchange_code_for_tokens("code")
        assert result is None


def test_exchange_code_request_exception(manager):
    import requests as req

    with patch("requests.post") as mock_post:
        mock_post.side_effect = req.exceptions.RequestException("Connection error")
        result = manager._exchange_code_for_tokens("code")
        assert result is None


def test_refresh_tokens_request_exception(manager):
    import requests as req

    with patch.object(manager.config, "get", return_value="refresh_token"), patch(
        "requests.post"
    ) as mock_post:
        mock_post.side_effect = req.exceptions.RequestException("Connection error")
        assert manager.refresh_tokens() is False


def test_refresh_tokens_no_access_token(manager):
    with patch.object(manager.config, "get", return_value="refresh_token"), patch(
        "requests.post"
    ) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.raise_for_status.return_value = None
        mock_post.return_value.json.return_value = {"error": "no token"}
        assert manager.refresh_tokens() is False
