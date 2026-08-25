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

An autouse fixture points CUPT_HOME at a temp directory for every test, so no
test can read or write the real ~/.cupt.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_cupt_home(tmp_path, monkeypatch):
    """Keep every test out of the developer's real ~/.cupt.

    `StateManager()` and `ConfigManager()` take no arguments in the CLI paths,
    so any test that exercises a command writes the active task, short IDs,
    and caches to the home directory of whoever runs pytest — clobbering their
    real active task. Point CUPT_HOME at a per-test directory instead.
    """
    monkeypatch.setenv("CUPT_HOME", str(tmp_path / "cupt-home"))


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.is_authenticated.return_value = True
    config.get.side_effect = lambda key, default=None: {
        "user.workspace_id": "workspace1",
        "user.user_id": "user1",
        "auth.access_token": "token123",
    }.get(key, default)
    config.load_cache.return_value = {}
    return config


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def fixture_json():
    def _load(relative_path: str):
        path = _FIXTURE_DIR / relative_path
        with open(path, "r") as f:
            return json.load(f)

    return _load
