"""Tests for the shared get_client_context() auth guard."""

from unittest.mock import patch

import click
import pytest

from cupt.context import get_client_context


def test_returns_context_when_authenticated():
    with patch("cupt.context.ConfigManager") as mock_cm, patch(
        "cupt.context.ClickUpClient"
    ) as mock_client_cls:
        mock_cm.return_value.is_authenticated.return_value = True
        mock_cm.return_value.get.side_effect = lambda k, d=None: {
            "user.workspace_id": "ws1",
            "auth.access_token": "tok",
        }.get(k, d)

        config, client, workspace_id = get_client_context()

        assert config is mock_cm.return_value
        assert client is mock_client_cls.return_value
        assert workspace_id == "ws1"


def test_exits_when_not_authenticated():
    with patch("cupt.context.ConfigManager") as mock_cm:
        mock_cm.return_value.is_authenticated.return_value = False
        with pytest.raises(click.exceptions.Exit) as exc:
            get_client_context()
        assert exc.value.exit_code == 2


def test_exits_when_workspace_id_missing():
    with patch("cupt.context.ConfigManager") as mock_cm, patch(
        "cupt.context.ClickUpClient"
    ):
        mock_cm.return_value.is_authenticated.return_value = True
        mock_cm.return_value.get.return_value = None
        with pytest.raises(click.exceptions.Exit) as exc:
            get_client_context(need_workspace=True)
        assert exc.value.exit_code == 2


def test_skips_workspace_check_when_not_required():
    with patch("cupt.context.ConfigManager") as mock_cm, patch(
        "cupt.context.ClickUpClient"
    ) as mock_client_cls:
        mock_cm.return_value.is_authenticated.return_value = True
        mock_cm.return_value.get.side_effect = lambda k, d=None: {
            "auth.access_token": "tok",
        }.get(k, d)  # no workspace_id
        config, client, workspace_id = get_client_context(need_workspace=False)
        assert client is mock_client_cls.return_value
        assert workspace_id is None
