"""
OAuth authentication for ClickUp API v1 (updated)
"""

import html
import secrets
import select
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

import click
import requests

from cupt.config import ConfigManager
from cupt.i18n import _, format_message


def print_info(message: str):
    print(f"ℹ️  {_(message)}")


def print_error(message: str):
    print(f"❌ {_(message)}")


def print_success(message: str):
    print(f"✅ {_(message)}")


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from ClickUp"""

    def __init__(self, auth_manager, *args, **kwargs):
        self.auth_manager = auth_manager
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET request for OAuth callback"""
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)

        # Check for authorization code
        if "code" in query_params:
            # Anything can reach a listening localhost port, so a code alone
            # proves nothing about who started this flow. Only accept a
            # callback carrying the state we generated for this session.
            if not self.auth_manager.verify_state(query_params.get("state", [None])[0]):
                self.auth_manager.state_mismatch = True
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h1>Authentication Failed</h1>"
                    b"<p>This callback did not match the pending sign-in. "
                    b"Nothing was saved.</p></body></html>"
                )
                return

            code = query_params["code"][0]

            # Send response to browser
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            success_html = """
            <html>
                <body>
                    <h1>Authentication Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
            </html>
            """
            self.wfile.write(success_html.encode())

            # Store code for main thread to process
            self.auth_manager.auth_code = code
            self.auth_manager.received = True
        elif "error" in query_params:
            error = query_params["error"][0]

            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()

            # `error` is attacker-controllable query-string text rendered on
            # the localhost origin — escape it rather than interpolating raw.
            error_html = f"""
            <html>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {html.escape(error)}</p>
                </body>
            </html>
            """
            self.wfile.write(error_html.encode())
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"Missing authorization code")

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


class OAuthManager:
    """Manage OAuth authentication flow"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.callback_port = 4321
        self.auth_code = None
        self.received = False
        self.state = secrets.token_urlsafe(32)
        self.state_mismatch = False
        self.config = ConfigManager()

    def verify_state(self, received: Optional[str]) -> bool:
        """Whether a callback's ``state`` belongs to this session."""
        if not received:
            return False
        return secrets.compare_digest(received, self.state)

    def authorize_url(self) -> str:
        """The ClickUp authorize URL for this session, state included."""
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": f"http://localhost:{self.callback_port}",
                "state": self.state,
            }
        )
        return f"https://app.clickup.com/api?{query}"

    def start_oauth_flow(self, no_browser: bool = False) -> Optional[Dict[str, Any]]:
        """Run the OAuth flow.

        ``no_browser`` skips straight to pasting the redirect by hand, which is
        the only thing that works when cupt runs somewhere the browser can't
        reach — see :meth:`_prompt_for_redirect`.
        """
        auth_url = self.authorize_url()

        if no_browser:
            print_info(_("Open this URL on a machine with a browser:"))
            print_info(auth_url)
            return self._prompt_for_redirect()

        print_info(_("Opening browser for authentication..."))
        print_info(
            format_message("If browser doesn't open, visit: {url}", url=auth_url)
        )

        # Open browser
        try:
            webbrowser.open(auth_url)
        except Exception as e:
            print_error(format_message("Could not open browser: {error}", error=e))
            print_info(_("Please manually visit the URL above"))

        # Start local server to handle callback
        return self._start_callback_server()

    def _can_watch_stdin(self) -> bool:
        """Whether the wait loop can offer the paste shortcut.

        ``select`` only accepts sockets on Windows, and a piped or closed stdin
        has no keypress to give, so the shortcut is TTY-only.
        """
        try:
            return sys.stdin is not None and sys.stdin.isatty()
        except (AttributeError, ValueError):
            return False

    @staticmethod
    def _parse_redirect(value: str) -> Tuple[Optional[str], Optional[str]]:
        """Pull ``(code, state)`` out of a pasted redirect URL or bare code."""
        value = value.strip().strip("\"'")
        if not value:
            return None, None
        if value.startswith("http") or "?" in value or "code=" in value:
            params = parse_qs(urlparse(value).query)
            return params.get("code", [None])[0], params.get("state", [None])[0]
        # A bare code, typed across by hand. There is no cross-site vector for
        # `state` to guard against when the user is the transport.
        return value, None

    def _prompt_for_redirect(self) -> Optional[Dict[str, Any]]:
        """Take the redirect by hand instead of catching it on a socket.

        The callback server listens on the host running cupt, so over SSH the
        browser's ``localhost`` is a different machine and the redirect never
        arrives. Pasting the URL closes that gap without a port-forward, and
        keeps the `state` check: it is validated out of the pasted URL exactly
        as it would be out of a real callback.
        """
        print_info(
            _(
                "Approve access in the browser, then copy the URL from its "
                "address bar. The page will fail to load — that is expected."
            )
        )
        try:
            pasted = click.prompt(
                _("Paste the redirect URL (or just the code)"), type=str
            )
        except (EOFError, click.Abort):
            print_error(_("Authentication cancelled"))
            return None

        code, state = self._parse_redirect(pasted)
        if not code:
            print_error(_("No authorization code found in that value."))
            return None
        if state is not None and not self.verify_state(state):
            print_error(
                _(
                    "That URL belongs to a different sign-in attempt. "
                    "Nothing was saved — run `cupt auth` again."
                )
            )
            return None
        return self._exchange_code_for_tokens(code)

    def _start_callback_server(self) -> Optional[Dict[str, Any]]:
        """Start local HTTP server for OAuth callback"""

        def handler(*args):
            return OAuthCallbackHandler(self, *args)

        try:
            print_info(
                format_message(
                    "Waiting for authentication on port {port}...",
                    port=self.callback_port,
                )
            )
            server = HTTPServer(("localhost", self.callback_port), handler)
            server.timeout = 120  # 2 minute timeout

            watch_stdin = self._can_watch_stdin()
            if watch_stdin:
                print_info(
                    _(
                        "Running cupt on another machine? The browser cannot reach "
                        "this host — press x then Enter to paste the URL instead."
                    )
                )

            # Poll the socket and the keyboard together so the paste shortcut
            # stays live for the whole wait rather than only after it expires.
            start_time = time.time()
            while (
                not self.received
                and not self.state_mismatch
                and (time.time() - start_time) < 120
            ):
                streams = [server] + ([sys.stdin] if watch_stdin else [])
                try:
                    readable = select.select(streams, [], [], 0.5)[0]
                except OSError:
                    # select() takes only sockets on Windows; drop the shortcut
                    # rather than the whole wait.
                    watch_stdin = False
                    continue
                if server in readable:
                    server.handle_request()
                    continue
                if watch_stdin and sys.stdin in readable:
                    if sys.stdin.readline().strip().lower() == "x":
                        server.server_close()
                        return self._prompt_for_redirect()

            server.server_close()

            if self.state_mismatch:
                print_error(
                    _(
                        "Rejected a sign-in callback that did not match this session. "
                        "Nothing was saved — run `cupt auth` again."
                    )
                )
                return None
            if self.received and self.auth_code:
                return self._exchange_code_for_tokens(self.auth_code)
            if watch_stdin:
                # A timeout on a remote box almost always means the redirect
                # went to the user's own machine. Offer the paste rather than
                # making them start over.
                print_info(_("No callback arrived on this host."))
                return self._prompt_for_redirect()
            print_error(_("Authentication timed out"))
            return None

        except OSError as e:
            if "Address already in use" in str(e):
                print_error(
                    format_message(
                        "Port {port} is already in use", port=self.callback_port
                    )
                )
                print_error(_("Please stop any other applications using this port"))
            else:
                print_error(
                    format_message("Failed to start callback server: {error}", error=e)
                )
            return None

    def _exchange_code_for_tokens(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        # Use OAuth v2 token endpoint as documented
        token_url = "https://api.clickup.com/api/v2/oauth/token"

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
        }

        try:
            response = requests.post(token_url, data=data)

            print_info(
                format_message(
                    "Token exchange response status: {status}",
                    status=response.status_code,
                )
            )

            if response.status_code != 200:
                print_error(
                    format_message(
                        "HTTP {status}: {body}",
                        status=response.status_code,
                        body=response.text,
                    )
                )
                return None

            response.raise_for_status()
            tokens = response.json()

            if "access_token" in tokens:
                # Store tokens in config
                self.config.set("auth.access_token", tokens["access_token"])
                if "refresh_token" in tokens:
                    self.config.set("auth.refresh_token", tokens["refresh_token"])

                # Store client identifier (do not persist client_secret)
                self.config.set("auth.client_id", self.client_id)

                print_success(_("Authentication successful!"))
                return tokens
            else:
                print_error(_("No access token received"))
                print_error(format_message("Response: {response}", response=tokens))
                return None

        except requests.exceptions.RequestException as e:
            print_error(
                format_message("Failed to exchange code for tokens: {error}", error=e)
            )
            return None
        except ValueError as e:
            print_error(
                format_message("Invalid response from token endpoint: {error}", error=e)
            )
            return None

    def refresh_tokens(self) -> bool:
        """Refresh access token using refresh token"""
        refresh_token = self.config.get("auth.refresh_token")

        if not refresh_token:
            print_error(_("No refresh token available"))
            return False

        token_url = "https://api.clickup.com/api/v2/oauth/token"

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()

            tokens = response.json()

            if "access_token" in tokens:
                self.config.set("auth.access_token", tokens["access_token"])
                if "refresh_token" in tokens:
                    self.config.set("auth.refresh_token", tokens["refresh_token"])

                print_success(_("Tokens refreshed successfully"))
                return True
            else:
                print_error(_("No access token received during refresh"))
                return False

        except requests.exceptions.RequestException as e:
            print_error(format_message("Failed to refresh tokens: {error}", error=e))
            return False
        except ValueError as e:
            print_error(
                format_message("Invalid response during refresh: {error}", error=e)
            )
            return False

    def logout(self):
        """Clear authentication data"""
        self.config.set("auth.access_token", None)
        self.config.set("auth.refresh_token", None)
        print_success(_("Logged out successfully"))
