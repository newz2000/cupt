"""
Main CLI interface for CUPT
"""

import logging
import sys

import click

from cupt import __version__
from cupt.active import active_cmd, start_cmd, stop_cmd
from cupt.add import add_cmd
from cupt.api import ClickUpClient
from cupt.attachments import attach_group
from cupt.auth import OAuthManager
from cupt.config import ConfigManager
from cupt.i18n import _, configure_language, format_message, translate_click_metadata
from cupt.notes import add_note, list_notes
from cupt.summary import summary_cmd
from cupt.tags import tag_group
from cupt.tasks import (
    complete_task_cmd,
    context_cmd,
    list_tasks_cmd,
    prefetch_cmd,
    show_task_cmd,
    statuses_cmd,
)
from cupt.time_tracker import time_group
from cupt.utils import (
    print_error,
    print_success,
    print_warning,
    set_interactive_override,
)
from cupt.work import work_cmd


def _set_interactive_callback(ctx, param, value):
    """Translate --interactive / --no-interactive into the global override."""
    if value is True:
        set_interactive_override(True)
    elif value is False:
        set_interactive_override(False)
    return value


def _set_language_callback(ctx, param, value):
    """Configure translations before Click renders command help."""
    configure_language(value)
    translate_click_metadata(ctx.find_root().command)
    return value


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--debug",
    is_flag=True,
    envvar="CUPT_DEBUG",
    help="Enable debug logging",
    is_eager=True,
    expose_value=False,
    callback=lambda ctx, param, val: (
        logging.basicConfig(
            level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s"
        )
        if val
        else None
    ),
)
@click.option(
    "--lang",
    envvar="CUPT_LANG",
    help="Language code for CLI messages (for example: en, es).",
    is_eager=True,
    expose_value=False,
    callback=_set_language_callback,
)
@click.option(
    "--interactive/--no-interactive",
    default=None,
    is_eager=True,
    expose_value=False,
    callback=_set_interactive_callback,
    help=(
        "Force interactive (short IDs + active task) or non-interactive mode. "
        "Default: enabled when stdout is a TTY."
    ),
)
def cli():
    """CUPT - ClickUp Task Management CLI"""


@cli.command()
def auth():
    """Authenticate with ClickUp using OAuth"""
    config = ConfigManager()

    # Check if already has personal token
    existing_token = config.get("auth.access_token")
    if existing_token and existing_token.startswith("pk_"):
        print_success(_("Already authenticated with Personal API Token"))
        return

    # Ask user which method to use
    click.echo(_("Choose authentication method:"))
    click.echo(_("1. OAuth (recommended for teams)"))
    click.echo(_("2. Personal API Token (simpler, individual use)"))
    choice = click.prompt(_("Enter choice (1 or 2)"), type=int, default=1)

    if choice == 2:
        # Personal API Token method
        click.echo("\n" + _("To get your Personal API Token:"))
        click.echo(_("1. Go to: https://app.clickup.com/settings/apps"))
        click.echo(_("2. Copy your Personal API Token (starts with 'pk_')"))
        click.echo()

        api_token = click.prompt(
            _("Enter your Personal API Token"), hide_input=True, type=str
        )

        if not api_token:
            print_error(_("API Token is required"))
            sys.exit(1)

        if not api_token.startswith("pk_"):
            print_error(_("Personal API tokens should start with 'pk_'"))
            sys.exit(1)

        # Store token
        config.set("auth.access_token", api_token)
        print_success(_("Authenticated with Personal API Token"))

        # Try to get user info
        try:
            client = ClickUpClient(api_token)
            user_info = client.get_user()
            workspaces = client.get_workspaces()

            if workspaces:
                config.set("user.workspace_id", workspaces[0]["id"])
                config.set("user.user_id", user_info["user"]["id"])
                print_success(
                    format_message(
                        "Authenticated as {username}",
                        username=user_info["user"]["username"],
                    )
                )
                print_success(
                    format_message(
                        "Default workspace: {workspace}",
                        workspace=workspaces[0]["name"],
                    )
                )

        except Exception as e:
            print_error(format_message("Failed to get user info: {error}", error=e))

    else:
        # OAuth method
        click.echo(
            "\n"
            + _("To authenticate with ClickUp, you'll need to create an OAuth app:")
        )
        click.echo(_("1. Go to: https://app.clickup.com/settings/apps"))
        click.echo(_("2. Click 'Create new app'"))
        click.echo(_("3. Set redirect URL to: http://localhost:4321"))
        click.echo(_("4. Copy your Client ID and Client Secret"))
        click.echo()

        client_id = click.prompt(_("Enter your ClickUp Client ID"), type=str)
        client_secret = click.prompt(
            _("Enter your ClickUp Client Secret"), hide_input=True, type=str
        )

        if not client_id or not client_secret:
            print_error(_("Client ID and Client Secret are required"))
            sys.exit(1)

        # Start OAuth flow
        oauth_manager = OAuthManager(client_id, client_secret)
        tokens = oauth_manager.start_oauth_flow()

        if tokens:
            # Get user info to populate team/user data
            try:
                client = ClickUpClient(tokens["access_token"])
                user_info = client.get_user()
                workspaces = client.get_workspaces()

                if workspaces:
                    # Set first workspace as default
                    config.set("user.workspace_id", workspaces[0]["id"])
                    config.set("user.user_id", user_info["user"]["id"])

                    print_success(
                        format_message(
                            "Authenticated as {username}",
                            username=user_info["user"]["username"],
                        )
                    )
                    print_success(
                        format_message(
                            "Default workspace: {workspace}",
                            workspace=workspaces[0]["name"],
                        )
                    )
                else:
                    print_warning(
                        _("No workspaces found - you may need to join one in ClickUp")
                    )

            except Exception as e:
                print_error(format_message("Failed to get user info: {error}", error=e))
        else:
            print_error(_("Authentication failed"))


@cli.command()
def logout():
    """Clear authentication data"""
    # Empty client_id/secret because we only want logout() to clear stored tokens.
    oauth_manager = OAuthManager("", "")
    oauth_manager.logout()


@cli.command()
def status():
    """Show authentication status and user info"""
    config = ConfigManager()

    if not config.is_authenticated():
        print_warning(_("Not authenticated. Run 'cupt auth' to authenticate."))
        return

    try:
        client = ClickUpClient(config.get("auth.access_token"))
        user_info = client.get_user()
        workspace_id = config.get("user.workspace_id")

        if workspace_id:
            workspaces = client.get_workspaces()
            current_ws = next((w for w in workspaces if w["id"] == workspace_id), None)
            workspace_name = current_ws["name"] if current_ws else _("Unknown")
        else:
            workspace_name = _("Not set")

        print_success(
            format_message(
                "Authenticated as: {username}",
                username=user_info["user"]["username"],
            )
        )
        print_success(
            format_message("Workspace: {workspace}", workspace=workspace_name)
        )

    except Exception as e:
        print_error(format_message("Failed to get status: {error}", error=e))


@cli.command()
@click.option("--workspace-id", help="Override workspace ID")
@click.option("--json", "as_json", is_flag=True, help="Output raw team data as JSON")
def teams(workspace_id, as_json):
    """List ClickUp teams (user-groups) in the workspace.

    Note: ClickUp calls user-groups "teams" in its UI; the underlying
    REST URL is `/group` for historical reasons.
    """
    import json as _json

    config = ConfigManager()
    if not config.is_authenticated():
        print_warning(_("Not authenticated. Run 'cupt auth' first."))
        return

    ws_id = workspace_id or config.get("user.workspace_id")
    if not ws_id:
        print_error(
            _("Workspace ID not set. Run 'cupt config --workspace-id <id>' first.")
        )
        return

    try:
        client = ClickUpClient(config.get("auth.access_token"))
        team_list = client.get_teams(ws_id)
    except Exception as e:
        print_error(format_message("Failed to fetch teams: {error}", error=e))
        return

    if as_json:
        click.echo(_json.dumps(team_list, indent=2))
        return

    if not team_list:
        print_warning(_("No teams found in this workspace."))
        return

    click.echo(f"\n{_('ID'):<14} {_('Members'):<8} {_('Name')}")
    click.echo("-" * 60)
    for t in team_list:
        tid = t.get("id", "?")
        name = t.get("name", "?")
        members = len(t.get("members") or [])
        click.echo(f"{tid:<14} {members:<8} {name}")


@cli.command()
@click.option("--workspace-id", help="Set default workspace ID")
@click.option("--default-list", help="Set default list ID")
@click.option("--api-token", help="Set Personal API Token (starts with pk_)")
@click.option("--clear-cache", is_flag=True, help="Clear persistent parent name cache")
@click.option("--show", is_flag=True, help="Show current configuration")
def config(workspace_id, default_list, api_token, clear_cache, show):
    """Manage configuration"""
    config_manager = ConfigManager()

    if clear_cache:
        config_manager.clear_cache()
        print_success(_("Persistent cache cleared"))
        return

    if show:
        click.echo(_("Current configuration:"))
        click.echo(
            f"  {_('Workspace ID')}: "
            f"{config_manager.get('user.workspace_id', _('Not set'))}"
        )
        click.echo(
            f"  {_('Default List ID')}: "
            f"{config_manager.get('user.default_list_id', _('Not set'))}"
        )
        click.echo(
            f"  {_('User ID')}: {config_manager.get('user.user_id', _('Not set'))}"
        )
        click.echo(
            f"  {_('Authenticated')}: "
            f"{_('Yes') if config_manager.is_authenticated() else _('No')}"
        )

        # Show if using personal token
        token = config_manager.get("auth.access_token")
        if token and token.startswith("pk_"):
            click.echo(f"  {_('Auth Method')}: {_('Personal API Token')}")
        else:
            click.echo(f"  {_('Auth Method')}: {_('OAuth')}")
        return

    if api_token:
        config_manager.set("auth.access_token", api_token)
        print_success(_("Personal API Token set"))

    if workspace_id:
        config_manager.set("user.workspace_id", workspace_id)
        print_success(
            format_message(
                "Workspace ID set to: {workspace_id}", workspace_id=workspace_id
            )
        )

    if default_list:
        config_manager.set("user.default_list_id", default_list)
        print_success(
            format_message("Default list ID set to: {list_id}", list_id=default_list)
        )

    if not workspace_id and not default_list and not api_token and not show:
        click.echo(click.get_current_context().get_help())


# Add commands
cli.add_command(list_tasks_cmd)
cli.add_command(show_task_cmd)
cli.add_command(complete_task_cmd)
cli.add_command(context_cmd)
cli.add_command(prefetch_cmd)
cli.add_command(statuses_cmd)

cli.add_command(time_group)
cli.add_command(tag_group)
cli.add_command(attach_group)

cli.add_command(add_note)
cli.add_command(list_notes)
cli.add_command(summary_cmd)
cli.add_command(work_cmd)

cli.add_command(start_cmd)
cli.add_command(stop_cmd)
cli.add_command(active_cmd)
cli.add_command(add_cmd)

if __name__ == "__main__":
    cli()
