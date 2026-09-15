"""CLI commands for reading and managing task dependencies."""

import json

import click

from cupt.context import get_client_context
from cupt.errors import fail
from cupt.i18n import format_message
from cupt.services.dependency_service import DependencyService
from cupt.utils import print_success


@click.group(name="dep")
def dep_group():
    """View and manage task dependencies"""
    pass


@dep_group.command("list")
@click.argument("task_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_dependencies(task_id, as_json):
    """Show what a task is waiting on and what it blocks"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        service = DependencyService(client)
        result = service.list_dependencies(task_id)
    except Exception as e:
        fail(format_message("Failed to list dependencies: {error}", error=e), e)

    if as_json:
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Dependencies for {task_id}")
    click.echo("Waiting on:")
    _echo_entries(result["waiting_on"])
    click.echo("Blocking:")
    _echo_entries(result["blocking"])


def _echo_entries(entries):
    """Print one line per dependency entry, or a plain "none" line."""
    if not entries:
        click.echo("  (none)")
        return
    for entry in entries:
        marker = "✓" if entry["complete"] else "·"
        name = entry["name"] or entry["id"]
        status = entry["status"] or "unknown"
        click.echo(f"  {marker} {name} ({entry['id']}) - {status}")


@dep_group.command("add")
@click.argument("task_id")
@click.option(
    "--waiting-on", "waiting_on", required=True, help="Task ID this task waits on"
)
def add_dependency(task_id, waiting_on):
    """Make a task wait on another task"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        service = DependencyService(client)
        service.add_dependency(task_id, waiting_on)
        print_success(
            format_message(
                "{task_id} now waits on {waiting_on}",
                task_id=task_id,
                waiting_on=waiting_on,
            )
        )
    except Exception as e:
        fail(format_message("Failed to add dependency: {error}", error=e), e)


@dep_group.command("rm")
@click.argument("task_id")
@click.option(
    "--waiting-on", "waiting_on", required=True, help="Task ID to stop waiting on"
)
def remove_dependency(task_id, waiting_on):
    """Remove a wait link between two tasks"""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        service = DependencyService(client)
        service.remove_dependency(task_id, waiting_on)
        print_success(
            format_message(
                "{task_id} no longer waits on {waiting_on}",
                task_id=task_id,
                waiting_on=waiting_on,
            )
        )
    except Exception as e:
        fail(format_message("Failed to remove dependency: {error}", error=e), e)
