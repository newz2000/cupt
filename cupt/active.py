"""
Active-task ("I'm working on this") commands: start, stop, active.

Interactive-only. Non-interactive callers see an error rather than silently
mutating ``state.json`` — scripts should pass explicit task IDs.
"""

from typing import Optional

import click

from cupt.context import get_client_context
from cupt.errors import EXIT_INVALID_INPUT, EXIT_NOT_FOUND, fail
from cupt.i18n import _, format_message
from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.state import StateManager
from cupt.utils import is_interactive, print_success, print_warning


def _require_interactive(command: str) -> bool:
    """Refuse a prompt-driven command in a non-interactive session.

    The contract calls this a clean failure, so it exits 4 rather than
    reporting success to whatever is scripting cupt.
    """
    if is_interactive():
        return True
    fail(
        format_message(
            "`cupt {command}` is interactive-only "
            "(set CUPT_INTERACTIVE=1 to force, or pass --interactive).",
            command=command,
        ),
        code=EXIT_INVALID_INPUT,
    )


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
        fail(str(e), e)

    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        task = client.get_task(resolved)
    except Exception as e:
        fail(format_message("Failed to look up task: {error}", error=e), e)

    if not task:
        fail(
            format_message("Task {task_id} not found.", task_id=resolved),
            code=EXIT_NOT_FOUND,
        )

    name = task.get("name") or resolved
    previous = state.set_active(resolved, name)
    if previous and previous.get("clickup_id") != resolved:
        print_warning(
            format_message(
                "Replaced active task {task_id} — {name}",
                task_id=previous["clickup_id"],
                name=previous.get("name", ""),
            )
        )
    print_success(
        format_message("Active: {task_id} — {name}", task_id=resolved, name=name)
    )


@click.command(name="stop")
def stop_cmd():
    """Clear the active task without marking it done."""
    if not _require_interactive("stop"):
        return
    state = StateManager()
    previous = state.clear_active()
    if previous:
        print_success(
            format_message(
                "Stopped: {task_id} — {name}",
                task_id=previous["clickup_id"],
                name=previous.get("name", ""),
            )
        )
    else:
        print_warning(_("No active task."))


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
        click.echo(_("No active task. Use `cupt start <id>` to set one."))
        return
    short = state.short_id_for(active["clickup_id"])
    short_prefix = f"[{short}] " if short else ""
    click.echo(
        format_message(
            "{prefix}{task_id}  {name}  · started {started_at}",
            prefix=short_prefix,
            task_id=active["clickup_id"],
            name=active.get("name", ""),
            started_at=active.get("started_at", ""),
        )
    )
