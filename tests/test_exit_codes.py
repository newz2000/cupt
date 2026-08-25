"""Contract tests for the exit codes in docs/agent-contract.md.

The codes are the whole reason an agent can trust cupt: without them a dead
token and an empty result set look identical. Every documented code gets a
test here so the table can't drift from the behavior again.
"""

from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from cupt.errors import (
    EXIT_API,
    EXIT_AUTH,
    EXIT_FAILURE,
    EXIT_INVALID_INPUT,
    EXIT_NOT_FOUND,
    EXIT_OK,
    exit_code_for,
)
from cupt.exceptions import APIError, AuthError, ConfigError
from cupt.main import cli
from cupt.resolver import IDResolutionError

# Every module that builds a client, so one patch set covers every command.
_COMMAND_MODULES = (
    "cupt.tasks",
    "cupt.summary",
    "cupt.work",
    "cupt.notes",
    "cupt.tags",
    "cupt.time_tracker",
    "cupt.attachments",
    "cupt.main",
)

# Commands that must report an authentication failure rather than succeed.
AUTHED_COMMANDS = [
    ["list", "--json"],
    ["show", "868abc", "--json"],
    ["context", "868abc"],
    ["statuses", "868abc", "--json"],
    ["summary", "--json"],
    ["teams", "--json"],
    ["work", "--json"],
    ["notes", "868abc"],
    ["tag", "add", "868abc", "x"],
    ["time", "status"],
    ["attach", "list", "868abc"],
    ["prefetch"],
]


# ---------------------------------------------------------------------------
# the mapping itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc,expected",
    [
        (AuthError("nope"), EXIT_AUTH),
        (ConfigError("nope"), EXIT_AUTH),
        (IDResolutionError("no short ID 5", not_found=True), EXIT_NOT_FOUND),
        (IDResolutionError("task ID required"), EXIT_INVALID_INPUT),
        (APIError("HTTP 404: not found"), EXIT_NOT_FOUND),
        (APIError("HTTP 401: Token invalid"), EXIT_API),
        (APIError("Request timed out after 30s"), EXIT_API),
        (ValueError("something else"), EXIT_FAILURE),
        (None, EXIT_FAILURE),
    ],
)
def test_exit_code_for(exc, expected):
    assert exit_code_for(exc) == expected


# ---------------------------------------------------------------------------
# 2 — authentication / configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("argv", AUTHED_COMMANDS, ids=lambda a: " ".join(a))
def test_unauthenticated_commands_exit_2(runner, argv):
    with patch("cupt.context.ConfigManager") as mock_config:
        mock_config.return_value.is_authenticated.return_value = False
        result = runner.invoke(cli, ["--no-interactive"] + argv)

    assert result.exit_code == EXIT_AUTH
    assert result.stdout == ""


def test_missing_workspace_exits_2(runner):
    with patch("cupt.context.ConfigManager") as mock_config:
        mock_config.return_value.is_authenticated.return_value = True
        mock_config.return_value.get.return_value = None
        result = runner.invoke(cli, ["--no-interactive", "list", "--json"])

    assert result.exit_code == EXIT_AUTH


# ---------------------------------------------------------------------------
# 5 — ClickUp API / network failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("argv", AUTHED_COMMANDS, ids=lambda a: " ".join(a))
def test_api_failure_exits_5_without_a_traceback(runner, mock_config, argv):
    """A dead token must never look like an empty result set."""
    client = MagicMock()
    for attr in (
        "get_workspace_tasks",
        "get_task",
        "get_list_statuses",
        "get_teams",
        "get_task_comments",
        "add_task_tag",
        "get_running_timer",
        "get_task_attachments",
        "start_timer",
    ):
        getattr(client, attr).side_effect = APIError("HTTP 401: Token invalid")

    ctx = (mock_config, client, "workspace1")
    with ExitStack() as stack:
        for module in _COMMAND_MODULES:
            stack.enter_context(patch(f"{module}.get_client_context", return_value=ctx))
        result = runner.invoke(cli, ["--no-interactive"] + argv)

    assert result.exit_code == EXIT_API, result.output
    assert "Traceback" not in result.output
    assert result.stdout == ""


# ---------------------------------------------------------------------------
# 4 — invalid input, including refusals that need a prompt
# ---------------------------------------------------------------------------


def test_missing_task_id_exits_4(runner):
    result = runner.invoke(cli, ["--no-interactive", "show", ""])
    assert result.exit_code == EXIT_INVALID_INPUT


def test_work_without_a_tty_exits_4(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = []
    with patch(
        "cupt.work.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(cli, ["--no-interactive", "work"])

    assert result.exit_code == EXIT_INVALID_INPUT


def test_start_without_a_tty_exits_4(runner):
    result = runner.invoke(cli, ["--no-interactive", "start", "868abc"])
    assert result.exit_code == EXIT_INVALID_INPUT


# ---------------------------------------------------------------------------
# 3 — not found
# ---------------------------------------------------------------------------


def test_unknown_short_id_exits_3(runner, mock_config, mock_client):
    with patch("cupt.utils.is_interactive", return_value=True), patch(
        "cupt.resolver.is_interactive", return_value=True
    ), patch(
        "cupt.tasks.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(cli, ["--interactive", "show", "999"])

    assert result.exit_code == EXIT_NOT_FOUND


def test_missing_task_exits_3(runner, mock_config, mock_client):
    mock_client.get_task.side_effect = APIError("HTTP 404: Task not found")
    with patch(
        "cupt.tasks.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(cli, ["--no-interactive", "show", "868abc"])

    assert result.exit_code == EXIT_NOT_FOUND


# ---------------------------------------------------------------------------
# 0 — success still means success
# ---------------------------------------------------------------------------


def test_success_exits_0(runner, mock_config, mock_client):
    mock_client.get_workspace_tasks.return_value = []
    with patch(
        "cupt.tasks.get_client_context",
        return_value=(mock_config, mock_client, "workspace1"),
    ):
        result = runner.invoke(cli, ["--no-interactive", "list", "--json"])

    assert result.exit_code == EXIT_OK
