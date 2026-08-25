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
        handler.path = f"/?code=testcode&state={manager.state}"
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


# ---------------------------------------------------------------------------
# OAuth state — the callback must belong to the session that started the flow
# ---------------------------------------------------------------------------


def _handler_for(manager, path):
    from cupt.auth import OAuthCallbackHandler

    with patch("http.server.BaseHTTPRequestHandler.__init__", return_value=None):
        handler = OAuthCallbackHandler(manager)
        handler.path = path
        handler.wfile = MagicMock()
        return handler


def _run(handler):
    with patch.object(handler, "send_response") as resp, patch.object(
        handler, "send_header"
    ), patch.object(handler, "end_headers"):
        handler.do_GET()
        return resp


def test_each_manager_gets_a_distinct_unguessable_state(tmp_path):
    with patch("cupt.auth.ConfigManager", return_value=ConfigManager(tmp_path / "c")):
        first = OAuthManager("id", "secret")
        second = OAuthManager("id", "secret")

    assert first.state != second.state
    assert len(first.state) >= 32


def test_authorize_url_carries_the_state(manager):
    with patch("cupt.auth.webbrowser.open") as mock_open, patch.object(
        manager, "_start_callback_server", return_value=None
    ):
        manager.start_oauth_flow()

    url = mock_open.call_args[0][0]
    assert f"state={manager.state}" in url
    assert "client_id=client_id" in url


def test_callback_without_state_is_rejected(manager):
    """Regression: a bare ?code= from any origin used to be accepted."""
    handler = _handler_for(manager, "/?code=attacker_code")
    resp = _run(handler)

    resp.assert_called_with(400)
    assert manager.auth_code is None
    assert manager.received is False
    assert manager.state_mismatch is True


def test_callback_with_wrong_state_is_rejected(manager):
    handler = _handler_for(manager, "/?code=attacker_code&state=not-the-right-one")
    resp = _run(handler)

    resp.assert_called_with(400)
    assert manager.auth_code is None
    assert manager.received is False


def test_verify_state_rejects_empty_and_none(manager):
    assert manager.verify_state(None) is False
    assert manager.verify_state("") is False
    assert manager.verify_state(manager.state) is True


def test_rejected_callback_ends_the_wait_without_exchanging(manager):
    """A mismatch must abort the flow, not sit out the 120s timeout."""
    manager.state_mismatch = True

    with patch("cupt.auth.HTTPServer") as mock_server, patch.object(
        manager, "_exchange_code_for_tokens"
    ) as mock_exchange:
        mock_server.return_value.handle_request.return_value = None
        result = manager._start_callback_server()

    assert result is None
    mock_exchange.assert_not_called()


def test_callback_server_reports_port_in_use(manager):
    with patch("cupt.auth.HTTPServer", side_effect=OSError("Address already in use")):
        assert manager._start_callback_server() is None
