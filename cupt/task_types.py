"""CLI command for discovering the workspace's task types."""

import json

import click

from cupt.context import get_client_context
from cupt.errors import EXIT_AUTH, fail
from cupt.i18n import _, format_message
from cupt.services.type_service import TypeService
from cupt.utils import print_warning


@click.command(name="types")
@click.option("--workspace-id", help="Override workspace ID")
@click.option("--json", "as_json", is_flag=True, help="Output raw type data as JSON")
def types_cmd(workspace_id, as_json):
    """List task types available for 'cupt list --type'.

    ClickUp calls these "custom items" in its API and "task types" in its UI.
    A task's type is an integer on the task; this is how you learn what the
    integers mean and what names `--type` accepts.
    """
    # --workspace-id may supply the workspace, so don't require a configured
    # one up front — but go through the shared guard so an unauthenticated
    # run exits 2 like every other command.
    _config, client, default_workspace = get_client_context(need_workspace=False)
    ws_id = workspace_id or default_workspace
    if not ws_id:
        fail(
            _("Workspace ID not set. Run 'cupt config --workspace-id <id>' first."),
            code=EXIT_AUTH,
        )

    try:
        type_list = TypeService(client).list_types(ws_id)
    except Exception as e:
        fail(format_message("Failed to fetch task types: {error}", error=e), e)

    if as_json:
        click.echo(json.dumps(type_list, indent=2))
        return

    if not type_list:
        print_warning(_("No task types found in this workspace."))
        return

    click.echo(f"\n{_('ID'):<8} {_('Name')}")
    click.echo("-" * 60)
    for t in type_list:
        click.echo(f"{str(t.get('id', '?')):<8} {t.get('name', '?')}")
