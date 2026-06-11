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

    client = ClickUpClient(config.get("auth.access_token"))
    return config, client, workspace_id
