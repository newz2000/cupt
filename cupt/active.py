"""
Active-task ("I'm working on this") commands: start, stop, active.

Interactive-only. Non-interactive callers see an error rather than silently
mutating ``state.json`` — scripts should pass explicit task IDs.
"""

from typing import Optional

import click

from cupt.context import get_client_context
from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.state import StateManager
from cupt.utils import is_interactive, print_error, print_success, print_warning


def _require_interactive(command: str) -> bool:
    if is_interactive():
        return True
    print_error(
        f"`cupt {command}` is interactive-only "
        "(set CUPT_INTERACTIVE=1 to force, or pass --interactive)."
    )
    return False


@click.command(name="start")
@click.argument("task_id", required=False)
def start_cmd(task_id: Optional[str]):
    """Mark a task as active for this session.

    Subsequent commands (`note`, `done`, `show`, ...) default to it until
    `cupt done` or `cupt stop` clears it. Interactive sessions only.
    """
    if not _require_interactive("start"):
        return

    state = StateManager()
    try:
        resolved = resolve_task_id(task_id, state=state, allow_active=False)
    except IDResolutionError as e:
        print_error(str(e))
        return

    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        task = client.get_task(resolved)
    except Exception as e:
        print_error(f"Failed to look up task: {e}")
        return

    if not task:
        print_error(f"Task {resolved} not found.")
        return

    name = task.get("name") or resolved
    previous = state.set_active(resolved, name)
    if previous and previous.get("clickup_id") != resolved:
        print_warning(
            f"Replaced active task {previous['clickup_id']} — {previous.get('name', '')}"
        )
    print_success(f"Active: {resolved} — {name}")


@click.command(name="stop")
def stop_cmd():
    """Clear the active task without marking it done."""
    if not _require_interactive("stop"):
        return
    state = StateManager()
    previous = state.clear_active()
    if previous:
        print_success(
            f"Stopped: {previous['clickup_id']} — {previous.get('name', '')}"
        )
    else:
        print_warning("No active task.")


@click.command(name="active")
def active_cmd():
    """Show the active task, if any."""
    if not is_interactive():
        # Read-only is harmless in scripts but emits no output; this keeps
        # `cupt active` usable as a quick "do I have an active task?" probe
        # while still not consulting state.json.
        return
    state = StateManager()
    active = state.get_active()
    if not active:
        click.echo("No active task. Use `cupt start <id>` to set one.")
        return
    short = state.short_id_for(active["clickup_id"])
    short_prefix = f"[{short}] " if short else ""
    click.echo(
        f"{short_prefix}{active['clickup_id']}  {active.get('name', '')}  "
        f"· started {active.get('started_at', '')}"
    )
