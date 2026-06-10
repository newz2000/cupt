from datetime import datetime

import click

from cupt.context import get_client_context
from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.services.time_service import TimeService
from cupt.utils import (
    format_duration,
    parse_duration,
    print_error,
    print_success,
    print_warning,
)


@click.group(name="time")
def time_group():
    """Time tracking commands"""
    pass


@time_group.command("start")
@click.argument("task_id", required=False)
def start_timer(task_id):
    """Start time tracking for a task. Falls back to the active task."""
    try:
        task_id = resolve_task_id(task_id)
    except IDResolutionError as e:
        print_error(str(e))
        return

    _, client, workspace_id = get_client_context()
    if not client:
        return

    try:
        service = TimeService(client, workspace_id)
        if service.get_running_timer():
            print_warning("Timer is already running. Stop current timer first.")
            return
        service.start_timer(task_id)
        print_success(f"Started tracking time for task {task_id}")
    except Exception as e:
        print_error(f"Failed to start timer: {e}")


@time_group.command("stop")
@click.argument("task_id", required=False)
def stop_timer(task_id=None):
    """Stop current time tracking"""
    _, client, workspace_id = get_client_context()
    if not client:
        return

    try:
        service = TimeService(client, workspace_id)
        if not service.get_running_timer():
            print_warning("No timer is currently running.")
            return
        service.stop_timer()
        print_success("Timer stopped")
    except Exception as e:
        print_error(f"Failed to stop timer: {e}")


@time_group.command("status")
def timer_status():
    """Show current timer status"""
    _, client, workspace_id = get_client_context()
    if not client:
        return

    try:
        service = TimeService(client, workspace_id)
        running_timer = service.get_running_timer()

        if running_timer:
            task_id = running_timer.get("task_id", "Unknown")
            start_time = running_timer.get("start", 0)
            click.echo("✅ Timer is running")
            click.echo(f"   Task ID: {task_id}")
            if start_time:
                start_dt = datetime.fromtimestamp(start_time / 1000)
                click.echo(f"   Started: {start_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print_warning("No timer is currently running")

    except Exception as e:
        print_error(f"Failed to get timer status: {e}")


@time_group.command("add")
@click.argument("args", nargs=-1, required=True)
@click.option("-m", "--message", help="Description for the time entry")
def add_time(args, message):
    """Add manual time entry to a task.

    Forms:

    \b
      cupt time add <task_id> <duration>   # explicit
      cupt time add <duration>             # uses active task (interactive)
    """
    if len(args) == 2:
        task_id_arg, duration = args
    elif len(args) == 1:
        task_id_arg, duration = None, args[0]
    else:
        print_error("Usage: cupt time add [<task_id>] <duration>")
        return

    try:
        task_id = resolve_task_id(task_id_arg)
    except IDResolutionError as e:
        print_error(str(e))
        return

    _, client, workspace_id = get_client_context()
    if not client:
        return

    duration_ms = parse_duration(duration)
    if duration_ms is None:
        print_error(f"Invalid duration format: {duration}")
        return

    try:
        TimeService(client, workspace_id).add_manual_time(task_id, duration_ms, message)
        print_success(f"Added {format_duration(duration_ms)} to task {task_id}")
        if message:
            print_success(f"Note: {message}")
    except Exception as e:
        print_error(f"Failed to add time entry: {e}")
