"""
Main CLI interface for CUPT
"""

import logging
import sys

import click

from cupt import __version__
from cupt.api import ClickUpClient
from cupt.attachments import attach_group
from cupt.auth import OAuthManager
from cupt.config import ConfigManager
from cupt.notes import add_note, list_notes
from cupt.summary import summary_cmd
from cupt.tags import tag_group
from cupt.tasks import (
    complete_task_cmd,
    context_cmd,
    list_tasks_cmd,
    prefetch_cmd,
    show_task_cmd,
)
from cupt.time_tracker import time_group
from cupt.utils import print_error, print_success, print_warning


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
def cli():
    """CUPT - ClickUp Task Management CLI"""
    pass


@cli.command()
def auth():
    """Authenticate with ClickUp using OAuth"""
    config = ConfigManager()

    # Check if already has personal token
    existing_token = config.get("auth.access_token")
    if existing_token and existing_token.startswith("pk_"):
        print_success("Already authenticated with Personal API Token")
        return

    # Ask user which method to use
    click.echo("Choose authentication method:")
    click.echo("1. OAuth (recommended for teams)")
    click.echo("2. Personal API Token (simpler, individual use)")
    choice = click.prompt("Enter choice (1 or 2)", type=int, default=1)

    if choice == 2:
        # Personal API Token method
        click.echo("\nTo get your Personal API Token:")
        click.echo("1. Go to: https://app.clickup.com/settings/apps")
        click.echo("2. Copy your Personal API Token (starts with 'pk_')")
        click.echo()

        api_token = click.prompt(
            "Enter your Personal API Token", hide_input=True, type=str
        )

        if not api_token:
            print_error("API Token is required")
            sys.exit(1)

        if not api_token.startswith("pk_"):
            print_error("Personal API tokens should start with 'pk_'")
            sys.exit(1)

        # Store token
        config.set("auth.access_token", api_token)
        print_success("Authenticated with Personal API Token")

        # Try to get user info
        try:
            client = ClickUpClient(api_token)
            user_info = client.get_user()
            teams = client.get_teams()

            if teams:
                config.set("user.team_id", teams[0]["id"])
                config.set("user.user_id", user_info["user"]["id"])
                print_success(f"Authenticated as {user_info['user']['username']}")
                print_success(f"Default team: {teams[0]['name']}")

        except Exception as e:
            print_error(f"Failed to get user info: {e}")

    else:
        # OAuth method
        click.echo(
            "\nTo authenticate with ClickUp, you'll need to create an OAuth app:"
        )
        click.echo("1. Go to: https://app.clickup.com/settings/apps")
        click.echo("2. Click 'Create new app'")
        click.echo("3. Set redirect URL to: http://localhost:4321")
        click.echo("4. Copy your Client ID and Client Secret")
        click.echo()

        client_id = click.prompt("Enter your ClickUp Client ID", type=str)
        client_secret = click.prompt(
            "Enter your ClickUp Client Secret", hide_input=True, type=str
        )

        if not client_id or not client_secret:
            print_error("Client ID and Client Secret are required")
            sys.exit(1)

        # Start OAuth flow
        oauth_manager = OAuthManager(client_id, client_secret)
        tokens = oauth_manager.start_oauth_flow()

        if tokens:
            # Get user info to populate team/user data
            try:
                client = ClickUpClient(tokens["access_token"])
                user_info = client.get_user()
                teams = client.get_teams()

                if teams:
                    # Set first team as default
                    config.set("user.team_id", teams[0]["id"])
                    config.set("user.user_id", user_info["user"]["id"])

                    print_success(f"Authenticated as {user_info['user']['username']}")
                    print_success(f"Default team: {teams[0]['name']}")
                else:
                    print_warning("No teams found - you may need to join a workspace")

            except Exception as e:
                print_error(f"Failed to get user info: {e}")
        else:
            print_error("Authentication failed")


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
        print_warning("Not authenticated. Run 'cupt auth' to authenticate.")
        return

    try:
        client = ClickUpClient(config.get("auth.access_token"))
        user_info = client.get_user()
        team_id = config.get("user.team_id")

        if team_id:
            teams = client.get_teams()
            current_team = next((t for t in teams if t["id"] == team_id), None)
            team_name = current_team["name"] if current_team else "Unknown"
        else:
            team_name = "Not set"

        print_success(f"Authenticated as: {user_info['user']['username']}")
        print_success(f"Team: {team_name}")

    except Exception as e:
        print_error(f"Failed to get status: {e}")


@cli.command()
@click.option("--team-id", help="Set default team ID")
@click.option("--default-list", help="Set default list ID")
@click.option("--api-token", help="Set Personal API Token (starts with pk_)")
@click.option("--clear-cache", is_flag=True, help="Clear persistent parent name cache")
@click.option("--show", is_flag=True, help="Show current configuration")
def config(team_id, default_list, api_token, clear_cache, show):
    """Manage configuration"""
    config_manager = ConfigManager()

    if clear_cache:
        config_manager.clear_cache()
        print_success("Persistent cache cleared")
        return

    if show:
        click.echo("Current configuration:")
        click.echo(f"  Team ID: {config_manager.get('user.team_id', 'Not set')}")
        click.echo(
            f"  Default List ID: {config_manager.get('user.default_list_id', 'Not set')}"
        )
        click.echo(f"  User ID: {config_manager.get('user.user_id', 'Not set')}")
        click.echo(
            f"  Authenticated: {'Yes' if config_manager.is_authenticated() else 'No'}"
        )

        # Show if using personal token
        token = config_manager.get("auth.access_token")
        if token and token.startswith("pk_"):
            click.echo("  Auth Method: Personal API Token")
        else:
            click.echo("  Auth Method: OAuth")
        return

    if api_token:
        config_manager.set("auth.access_token", api_token)
        print_success("Personal API Token set")

    if team_id:
        config_manager.set("user.team_id", team_id)
        print_success(f"Team ID set to: {team_id}")

    if default_list:
        config_manager.set("user.default_list_id", default_list)
        print_success(f"Default list ID set to: {default_list}")

    if not team_id and not default_list and not api_token and not show:
        click.echo(click.get_current_context().get_help())


# Add commands
cli.add_command(list_tasks_cmd)
cli.add_command(show_task_cmd)
cli.add_command(complete_task_cmd)
cli.add_command(context_cmd)
cli.add_command(prefetch_cmd)

cli.add_command(time_group)
cli.add_command(tag_group)
cli.add_command(attach_group)

cli.add_command(add_note)
cli.add_command(list_notes)
cli.add_command(summary_cmd)

if __name__ == "__main__":
    cli()
