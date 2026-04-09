"""
Shared fixtures for the CUPT test suite.

CLI tests patch the module-level ``get_client_context`` import rather than
the underlying ``ConfigManager`` / ``ClickUpClient`` classes directly, which
keeps each test independent of internal construction details.

Pattern for authenticated CLI tests:
    with patch('cupt.<module>.get_client_context', return_value=(mock_config, mock_client, 'team1')):
        ...

Pattern for auth-error tests (testing the guard itself):
    with patch('cupt.context.ConfigManager') as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        ...
"""

from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.is_authenticated.return_value = True
    config.get.side_effect = lambda key, default=None: {
        "user.team_id": "team1",
        "user.user_id": "user1",
        "auth.access_token": "token123",
    }.get(key, default)
    config.load_cache.return_value = {}
    return config


@pytest.fixture
def mock_client():
    return MagicMock()
