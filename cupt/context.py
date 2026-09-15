"""
Shared CLI context: authentication guard and client construction.

Every authenticated command calls get_client_context() instead of
duplicating the ConfigManager / ClickUpClient boilerplate inline.
"""

from typing import Optional, Tuple

import click

from cupt.api import ClickUpClient
from cupt.config import ConfigManager
from cupt.utils import print_error


def get_client_context(
    need_workspace: bool = True,
) -> Tuple[Optional[ConfigManager], Optional[ClickUpClient], Optional[str]]:
    """
    Build (config, client, workspace_id) for an authenticated command.

    Prints an actionable error and exits with code 2 if authentication
    or workspace preconditions are not met.

    Args:
        need_workspace: When True (default) also validates that a workspace
                        ID is configured.  Pass False for commands (e.g.
                        notes) that do not require one.
    """
    config = ConfigManager()

    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        raise click.exceptions.Exit(2)

    workspace_id = config.get("user.workspace_id")
    if need_workspace and not workspace_id:
        print_error(
            "Workspace ID not set. Run 'cupt config --workspace-id <id>' first."
        )
        raise click.exceptions.Exit(2)

    client = ClickUpClient(
        config.get("auth.access_token"), identity=identity_label(config)
    )
    return config, client, workspace_id


def identity_label(config: ConfigManager) -> Optional[str]:
    """A human-readable label for the account the token belongs to.

    Used only to say who a 401/403 refused. The id leads because names are not
    unique — one human or bot can hold several accounts in a workspace.
    """
    user_id = config.get("user.user_id")
    username = config.get("user.username")
    if user_id and username:
        return f"user {user_id} ({username})"
    return str(user_id or username) if (user_id or username) else None
