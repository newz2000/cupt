"""
``cupt add`` — quick capture of new tasks during work.

Intent: low-friction capture when you realize a new task needs to exist.
Not a project-management interface — defaults assume you're a person doing
work, and Hermes (or any other agent) gets the same surface with explicit
flags instead of inferred context.

Defaults in interactive mode when an active task is set:

- List: the active task's list (so capture lands next to what you were doing).
- Assignee: the authenticated user.
- No relationship to anything else; pass ``--blocks`` or ``--parent`` to
  link the new task to the active one (or to a specific ID).

In non-interactive mode the active task is invisible, so ``--list`` (or the
``user.default_list_id`` config fallback) is required.
"""

import json
from typing import Optional

import click

from cupt.context import get_client_context
from cupt.i18n import _, format_message
from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.state import StateManager
from cupt.utils import (
    is_interactive,
    parse_due_date,
    print_error,
    print_success,
    print_warning,
)

# Sentinel meaning "use the active task" for --blocks / --parent.
# (Click 8.3's parser no longer supports `is_flag=False, flag_value=...`
# without a following arg, so we require the explicit form `--blocks this`.)
_THIS = "this"


def _resolve_link_target(
    raw: Optional[str], state: StateManager, label: str
) -> Optional[str]:
    """Resolve --blocks / --parent value to a ClickUp ID.

    None  -> no link (flag not given)
    "this" -> active task (errors clearly if none set)
    int   -> short ID
    str   -> alphanumeric passthrough
    """
    if raw is None:
        return None
    if raw == _THIS:
        active = state.get_active()
        if not active:
            raise IDResolutionError(
                format_message(
                    "`--{label}` (without an ID) needs an active task. "
                    "Use `cupt start <id>` or pass `--{label} <id>` explicitly.",
                    label=label,
                )
            )
        return active["clickup_id"]
    return resolve_task_id(raw, state=state, allow_active=False)


@click.command(name="add")
@click.argument("name")
@click.option(
    "--list",
    "list_id",
    help="Target list ID (defaults to active task's list, then user.default_list_id)",
)
@click.option(
    "--parent",
    default=None,
    help=(
        "Make the new task a subtask. Pass an ID, a short ID, or `this` to "
        "use the active task."
    ),
)
@click.option(
    "--blocks",
    default=None,
    help=(
        "Make the new task a blocker on the given task (it will depend on "
        "the new one). Pass an ID, a short ID, or `this` to use the active "
        "task."
    ),
)
@click.option("--description", "-d", help="Task description")
@click.option(
    "--due",
    help=(
        "Due date: today, tomorrow, +Nd, +Nw, +Nh, YYYY-MM-DD, "
        "YYYY-MM-DD HH:MM, or raw epoch ms."
    ),
)
@click.option(
    "--tag",
    "tags",
    multiple=True,
    help="Tag to apply (repeatable).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output the created task as JSON (id, url, full payload).",
)
def add_cmd(
    name: str,
    list_id: Optional[str],
    parent: Optional[str],
    blocks: Optional[str],
    description: Optional[str],
    due: Optional[str],
    tags,
    as_json: bool,
):
    """Add a new task. One required positional: the task name.

    \b
    Interactive defaults: list inferred from active task; assignee = you.
    Pass `--blocks this` / `--parent this` to link the new task to the
    active one, or `--blocks <id>` / `--parent <id>` to link to a specific
    task.
    """
    config, client, _workspace_id = get_client_context(need_workspace=False)
    if not client:
        return

    state = StateManager() if is_interactive() else None

    # --- resolve target list -------------------------------------------------
    if not list_id:
        if state is not None:
            active = state.get_active()
            if active:
                try:
                    active_task = client.get_task(active["clickup_id"])
                    list_id = (active_task.get("list") or {}).get("id")
                except Exception:
                    list_id = None
        if not list_id:
            list_id = config.get("user.default_list_id")

    if not list_id:
        print_error(
            _(
                "No list specified. Pass `--list <id>` or set a default with "
                "`cupt config --default-list <id>`."
            )
        )
        return

    # --- resolve --parent and --blocks --------------------------------------
    link_state = state if state is not None else StateManager()
    try:
        parent_id = _resolve_link_target(parent, link_state, "parent")
        blocks_id = _resolve_link_target(blocks, link_state, "blocks")
    except IDResolutionError as e:
        print_error(str(e))
        return

    # --- build payload -------------------------------------------------------
    payload = {"name": name}

    user_id = config.get("user.user_id")
    if user_id:
        # ClickUp expects numeric assignee IDs in an int array.
        try:
            payload["assignees"] = [int(user_id)]
        except (TypeError, ValueError):
            pass  # fall through; ClickUp will create the task unassigned

    if description:
        payload["description"] = description

    if due:
        try:
            payload["due_date"] = parse_due_date(due)
            payload["due_date_time"] = True
        except ValueError as e:
            print_error(str(e))
            return

    if tags:
        payload["tags"] = list(tags)

    if parent_id:
        payload["parent"] = parent_id

    # --- create + link -------------------------------------------------------
    try:
        created = client.create_task(list_id, payload)
    except Exception as e:
        print_error(format_message("Failed to create task: {error}", error=e))
        return

    new_id = created.get("id")

    if blocks_id and new_id:
        # ClickUp's dependency endpoint: the blocked task is the URL path,
        # `depends_on` is the blocker. We want the named task to depend on
        # the new one (i.e. the new task blocks it).
        try:
            client.add_task_dependency(blocks_id, depends_on=new_id)
        except Exception as e:
            print_warning(
                format_message(
                    "Task created ({task_id}) but failed to add dependency on "
                    "{blocks_id}: {error}",
                    task_id=new_id,
                    blocks_id=blocks_id,
                    error=e,
                )
            )

    if as_json:
        click.echo(json.dumps(created, indent=2))
        return

    # Concise success line — capture should feel weightless.
    parts = [format_message("Created task {task_id}", task_id=new_id)]
    if parent_id:
        parts.append(format_message("(subtask of {parent_id})", parent_id=parent_id))
    if blocks_id:
        parts.append(format_message("(blocks {blocks_id})", blocks_id=blocks_id))
    print_success(" ".join(parts) + f": {name}")
