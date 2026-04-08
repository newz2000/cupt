"""
Shared CLI context: authentication guard and client construction.

Every authenticated command calls get_client_context() instead of
duplicating the ConfigManager / ClickUpClient boilerplate inline.
"""

from typing import Optional, Tuple

from cupt.api import ClickUpClient
from cupt.config import ConfigManager
from cupt.utils import print_error


def get_client_context(
    need_team: bool = True,
) -> Tuple[Optional[ConfigManager], Optional[ClickUpClient], Optional[str]]:
    """
    Build (config, client, team_id) for an authenticated command.

    Returns (None, None, None) and prints an actionable error if the
    preconditions are not met.  Callers should check ``if not client``
    before proceeding.

    Args:
        need_team: When True (default) also validates that a team ID is
                   configured.  Pass False for commands (e.g. notes) that
                   do not require a team ID.
    """
    config = ConfigManager()

    if not config.is_authenticated():
        print_error("Not authenticated. Run 'cupt auth' to authenticate.")
        return None, None, None

    team_id = config.get("user.team_id")
    if need_team and not team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return None, None, None

    client = ClickUpClient(config.get("auth.access_token"))
    return config, client, team_id
