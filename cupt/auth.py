"""
OAuth authentication for ClickUp API v1 (updated)
"""

import webbrowser
import urllib.parse
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any
import requests

from cupt.config import ConfigManager

def print_info(message: str):
    print(f"ℹ️  {message}")

def print_error(message: str):
    print(f"❌ {message}")

def print_success(message: str):
    print(f"✅ {message}")

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
        if 'code' in query_params:
            code = query_params['code'][0]
            
            # Send response to browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
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
        elif 'error' in query_params:
            error = query_params['error'][0]
            
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            error_html = f"""
            <html>
                <body>
                    <h1>Authentication Failed</h1>
                    <p>Error: {error}</p>
                </body>
            </html>
            """
            self.wfile.write(error_html.encode())
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
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
        self.config = ConfigManager()
    
    def start_oauth_flow(self) -> Optional[Dict[str, Any]]:
        """Start OAuth authentication flow"""
        # Use OAuth v2 authorize endpoint as documented
        redirect_uri = f"http://localhost:{self.callback_port}"
        
        # Use OAuth v2 authorize endpoint with proper encoding
        auth_url = f"https://app.clickup.com/api?client_id={self.client_id}&redirect_uri={redirect_uri}"
        
        print_info("Opening browser for authentication...")
        print_info(f"If browser doesn't open, visit: {auth_url}")
        
        # Open browser
        try:
            webbrowser.open(auth_url)
        except Exception as e:
            print_error(f"Could not open browser: {e}")
            print_info("Please manually visit the URL above")
        
        # Start local server to handle callback
        return self._start_callback_server()
    
    def _start_callback_server(self) -> Optional[Dict[str, Any]]:
        """Start local HTTP server for OAuth callback"""
        handler = lambda *args: OAuthCallbackHandler(self, *args)
        
        try:
            print_info(f"Waiting for authentication on port {self.callback_port}...")
            server = HTTPServer(('localhost', self.callback_port), handler)
            server.timeout = 120  # 2 minute timeout
            
            # Start server in current thread (blocks until callback or timeout)
            start_time = time.time()
            while not self.received and (time.time() - start_time) < 120:
                server.handle_request()
                time.sleep(0.1)
            
            server.server_close()
            
            if self.received and self.auth_code:
                return self._exchange_code_for_tokens(self.auth_code)
            else:
                print_error("Authentication timed out")
                return None
                
        except OSError as e:
            if "Address already in use" in str(e):
                print_error(f"Port {self.callback_port} is already in use")
                print_error("Please stop any other applications using this port")
            else:
                print_error(f"Failed to start callback server: {e}")
            return None
    
    def _exchange_code_for_tokens(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        # Use OAuth v2 token endpoint as documented
        token_url = "https://api.clickup.com/api/v2/oauth/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }
        
        try:
            response = requests.post(token_url, data=data)
            
            print_info(f"Token exchange response status: {response.status_code}")
            
            if response.status_code != 200:
                print_error(f"HTTP {response.status_code}: {response.text}")
                return None
            
            response.raise_for_status()
            tokens = response.json()
            
            print_info(f"Token response: {tokens}")
            
            if 'access_token' in tokens:
                # Store tokens in config
                self.config.set('auth.access_token', tokens['access_token'])
                if 'refresh_token' in tokens:
                    self.config.set('auth.refresh_token', tokens['refresh_token'])
                
                # Store client credentials
                self.config.set('auth.client_id', self.client_id)
                self.config.set('auth.client_secret', self.client_secret)
                
                print_success("Authentication successful!")
                return tokens
            else:
                print_error("No access token received")
                print_error(f"Response: {tokens}")
                return None
                
        except requests.exceptions.RequestException as e:
            print_error(f"Failed to exchange code for tokens: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print_error(f"Response text: {e.response.text}")
            return None
        except ValueError as e:
            print_error(f"Invalid response from token endpoint: {e}")
            return None
    
    def refresh_tokens(self) -> bool:
        """Refresh access token using refresh token"""
        refresh_token = self.config.get('auth.refresh_token')
        
        if not refresh_token:
            print_error("No refresh token available")
            return False
        
        token_url = "https://api.clickup.com/api/v2/oauth/token"
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            
            tokens = response.json()
            
            if 'access_token' in tokens:
                self.config.set('auth.access_token', tokens['access_token'])
                if 'refresh_token' in tokens:
                    self.config.set('auth.refresh_token', tokens['refresh_token'])
                
                print_success("Tokens refreshed successfully")
                return True
            else:
                print_error("No access token received during refresh")
                return False
                
        except requests.exceptions.RequestException as e:
            print_error(f"Failed to refresh tokens: {e}")
            return False
        except ValueError as e:
            print_error(f"Invalid response during refresh: {e}")
            return False
    
    def logout(self):
        """Clear authentication data"""
        self.config.set('auth.access_token', None)
        self.config.set('auth.refresh_token', None)
        print_success("Logged out successfully")