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


def test_callback_error_page_escapes_the_query_string(manager):
    """Regression: the error param was interpolated into HTML unescaped."""
    handler = _handler_for(manager, "/?error=%3Cscript%3Ealert(1)%3C/script%3E")
    _run(handler)

    body = b"".join(call.args[0] for call in handler.wfile.write.call_args_list)
    assert b"<script>" not in body
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in body


# ---------------------------------------------------------------------------
# remote sign-in: paste the redirect instead of catching it on a socket
# ---------------------------------------------------------------------------


def _redirect(manager, code="GOOD", state=None):
    state = manager.state if state is None else state
    return f"http://localhost:4321/?code={code}&state={state}"


def test_parse_redirect_accepts_a_full_url(manager):
    code, state = manager._parse_redirect(_redirect(manager))
    assert code == "GOOD"
    assert state == manager.state


def test_parse_redirect_tolerates_surrounding_quotes(manager):
    code, _state = manager._parse_redirect(f'"{_redirect(manager)}"')
    assert code == "GOOD"


def test_parse_redirect_accepts_a_bare_code(manager):
    assert manager._parse_redirect("  ABC123  ") == ("ABC123", None)


def test_parse_redirect_rejects_a_url_without_a_code(manager):
    assert manager._parse_redirect("http://localhost:4321/?error=denied")[0] is None
    assert manager._parse_redirect("")[0] is None


def test_pasted_redirect_with_matching_state_exchanges(manager):
    with patch.object(
        manager, "_exchange_code_for_tokens", return_value={"access_token": "t"}
    ) as exchange, patch("cupt.auth.click.prompt", return_value=_redirect(manager)):
        result = manager._prompt_for_redirect()

    assert result == {"access_token": "t"}
    exchange.assert_called_once_with("GOOD")


def test_pasted_redirect_with_wrong_state_is_refused(manager):
    """The paste path keeps the CSRF check rather than exempting remote users."""
    with patch.object(manager, "_exchange_code_for_tokens") as exchange, patch(
        "cupt.auth.click.prompt", return_value=_redirect(manager, "EVIL", "attacker")
    ):
        result = manager._prompt_for_redirect()

    assert result is None
    exchange.assert_not_called()


def test_pasted_bare_code_is_accepted(manager):
    """No state to check when the user carried the value across by hand."""
    with patch.object(
        manager, "_exchange_code_for_tokens", return_value={"access_token": "t"}
    ) as exchange, patch("cupt.auth.click.prompt", return_value="BARECODE"):
        manager._prompt_for_redirect()

    exchange.assert_called_once_with("BARECODE")


def test_pasted_url_without_a_code_reports_and_stops(manager):
    with patch.object(manager, "_exchange_code_for_tokens") as exchange, patch(
        "cupt.auth.click.prompt", return_value="http://localhost:4321/?error=denied"
    ):
        assert manager._prompt_for_redirect() is None

    exchange.assert_not_called()


def test_no_browser_skips_the_socket_entirely(manager):
    with patch.object(
        manager, "_prompt_for_redirect", return_value={"access_token": "t"}
    ) as prompt, patch.object(manager, "_start_callback_server") as server, patch(
        "cupt.auth.webbrowser.open"
    ) as browser:
        result = manager.start_oauth_flow(no_browser=True)

    assert result == {"access_token": "t"}
    prompt.assert_called_once()
    server.assert_not_called()
    browser.assert_not_called()


def test_authorize_url_is_shown_for_no_browser(manager, capsys):
    with patch.object(manager, "_prompt_for_redirect", return_value=None):
        manager.start_oauth_flow(no_browser=True)

    assert manager.authorize_url() in capsys.readouterr().out


def test_pressing_x_during_the_wait_switches_to_paste(manager):
    """The shortcut must be live during the wait, not only after it expires."""
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = True
    fake_stdin.readline.return_value = "x\n"

    with patch("cupt.auth.HTTPServer") as server_cls, patch(
        "cupt.auth.sys.stdin", fake_stdin
    ), patch(
        "cupt.auth.select.select", return_value=([fake_stdin], [], [])
    ), patch.object(
        manager, "_prompt_for_redirect", return_value={"access_token": "t"}
    ) as prompt:
        result = manager._start_callback_server()

    assert result == {"access_token": "t"}
    prompt.assert_called_once()
    server_cls.return_value.server_close.assert_called_once()


def test_timeout_offers_the_paste_when_interactive(manager):
    """A timeout on a remote host means the redirect went elsewhere."""
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = True

    with patch("cupt.auth.HTTPServer"), patch("cupt.auth.sys.stdin", fake_stdin), patch(
        "cupt.auth.select.select", return_value=([], [], [])
    ), patch("cupt.auth.time.time", side_effect=[0, 0, 999]), patch.object(
        manager, "_prompt_for_redirect", return_value={"access_token": "t"}
    ) as prompt:
        result = manager._start_callback_server()

    assert result == {"access_token": "t"}
    prompt.assert_called_once()


def test_non_tty_never_offers_the_paste(manager):
    """Scripts get the old clean timeout, not a prompt they cannot answer."""
    fake_stdin = MagicMock()
    fake_stdin.isatty.return_value = False

    with patch("cupt.auth.HTTPServer"), patch("cupt.auth.sys.stdin", fake_stdin), patch(
        "cupt.auth.select.select", return_value=([], [], [])
    ), patch("cupt.auth.time.time", side_effect=[0, 0, 999]), patch.object(
        manager, "_prompt_for_redirect"
    ) as prompt:
        result = manager._start_callback_server()

    assert result is None
    prompt.assert_not_called()
