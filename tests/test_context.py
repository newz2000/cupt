"""Tests for the shared get_client_context() auth guard."""

from unittest.mock import MagicMock, patch
from cupt.context import get_client_context


def test_returns_context_when_authenticated():
    with patch("cupt.context.ConfigManager") as mock_cm, \
         patch("cupt.context.ClickUpClient") as mock_client_cls:
        mock_cm.return_value.is_authenticated.return_value = True
        mock_cm.return_value.get.side_effect = lambda k, d=None: {
            "user.team_id": "team1",
            "auth.access_token": "tok",
        }.get(k, d)

        config, client, team_id = get_client_context()

        assert config is mock_cm.return_value
        assert client is mock_client_cls.return_value
        assert team_id == "team1"


def test_returns_none_when_not_authenticated():
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        config, client, team_id = get_client_context()
        assert client is None
        assert config is None
        assert team_id is None


def test_returns_none_when_team_id_missing():
    with patch("cupt.context.ConfigManager") as mock_cm, \
         patch("cupt.context.ClickUpClient"):
        mock_cm.return_value.is_authenticated.return_value = True
        mock_cm.return_value.get.return_value = None
        config, client, team_id = get_client_context(need_team=True)
        assert client is None


def test_skips_team_check_when_not_required():
    with patch("cupt.context.ConfigManager") as mock_cm, \
         patch("cupt.context.ClickUpClient") as mock_client_cls:
        mock_cm.return_value.is_authenticated.return_value = True
        mock_cm.return_value.get.side_effect = lambda k, d=None: {
            "auth.access_token": "tok",
        }.get(k, d)  # no team_id
        config, client, team_id = get_client_context(need_team=False)
        assert client is mock_client_cls.return_value
        assert team_id is None
