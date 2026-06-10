import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import click

from cupt.context import get_client_context
from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.services.task_service import TaskService
from cupt.state import StateManager
from cupt.utils import (
    format_date,
    format_duration,
    get_terminal_width,
    is_interactive,
    print_error,
    print_success,
    print_warning,
    truncate_text,
)

# Fixed column widths in the list view (excluding the trailing name column).
# Non-verbose: "{id:<12} {status:<12} {due:<18} {name}" -> 12+1+12+1+18+1 = 45
# Verbose adds " {assignee:<18} {est:<8} {tracked:<8}" -> +18+1+8+1+8+1 = 37
_LIST_FIXED_WIDTH = 45
_LIST_FIXED_WIDTH_VERBOSE = 82
# Short-ID column ("#") prefixed in interactive sessions: "{#:<4} " -> 5
_SHORT_ID_COLUMN_WIDTH = 5


def _name_column_width(verbose: bool, with_short: bool = False) -> Optional[int]:
    """Available columns for the name field, or None when output isn't a TTY."""
    width = get_terminal_width()
    if width is None:
        return None
    fixed = _LIST_FIXED_WIDTH_VERBOSE if verbose else _LIST_FIXED_WIDTH
    if with_short:
        fixed += _SHORT_ID_COLUMN_WIDTH
    return max(10, width - fixed)


def _print_team_filter_footer(service, elapsed: float, mine: bool) -> None:
    """Show how much work the --team filter cost, and hint when truncated.

    Team filtering is client-side (ClickUp has no server-side group filter),
    so we walk extra pages to widen the candidate set. Surfacing the cost
    keeps the latency honest, and the cap-reached hint warns the user when
    matches may still be missing on further pages.
    """
    pages = getattr(service, "last_pages_walked", 0)
    if pages <= 1:
        return  # snappy result; no need to clutter output

    page_cap = 15 if mine else 10
    msg = f"(team filter: searched {pages} pages in {elapsed:.1f}s"
    if pages >= page_cap:
        msg += "; hit page cap — pair with --tag for full coverage"
    msg += ")"
    click.echo(msg, err=True)


def _separator_width(verbose: bool) -> int:
    """Width of the dashed separator under the header."""
    width = get_terminal_width()
    if width is not None:
        return width
    return 140 if verbose else 120


def _render_task_list(
    tasks,
    verbose: bool,
    parent_cache,
    short_map=None,
) -> None:
    """Print the task table. ``short_map`` (clickup_id → short str) prepends a
    ``[N]`` column when present; ``None`` matches the legacy script-friendly
    output."""
    with_short = short_map is not None
    name_width = _name_column_width(verbose, with_short=with_short)

    short_header = f"{'#':<4} " if with_short else ""
    if verbose:
        click.echo(
            f"\n{short_header}"
            f"{'ID':<12} {'Status':<12} {'Due':<18} {'Assignee':<18} "
            f"{'Est':<8} {'Tracked':<8} {'Name'}"
        )
    else:
        click.echo(
            f"\n{short_header}{'ID':<12} {'Status':<12} {'Due':<18} {'Name'}"
        )
    click.echo("-" * _separator_width(verbose))

    for task in tasks:
        task_id = task.get("id", "No ID")
        status = task.get("status", {}).get("status", "unknown")
        due_date = format_date(task.get("due_date"))
        name = task.get("name", "No name")
        p_id = task.get("parent")

        if p_id:
            p_name = parent_cache.get(p_id, p_id)
            name = f"↳ {name} (sub of {p_name})"

        name = truncate_text(name, name_width)

        short_cell = ""
        if with_short:
            short = short_map.get(task_id, "")
            short_cell = f"{short:<4} "

        if verbose:
            individuals = [a.get("username", "?") for a in task.get("assignees", [])]
            team_chips = [
                f"[{g.get('name', '?')}]" for g in task.get("group_assignees", [])
            ]
            assignee = ", ".join(individuals + team_chips) or "-"
            est = (
                format_duration(task.get("time_estimate") or 0)
                if task.get("time_estimate")
                else "-"
            )
            tracked = (
                format_duration(int(task.get("time_spent") or 0))
                if task.get("time_spent")
                else "-"
            )
            click.echo(
                f"{short_cell}{task_id:<12} {status:<12} {due_date:<18} "
                f"{assignee:<18} {est:<8} {tracked:<8} {name}"
            )
        else:
            click.echo(
                f"{short_cell}{task_id:<12} {status:<12} {due_date:<18} {name}"
            )


def _print_active_footer(state: StateManager) -> None:
    """One-line reminder of what `cupt start` set and how stale the list is.

    Mitigates the "wrong terminal" mistake — every list ends with a clear
    statement of which task subsequent commands would mutate.
    """
    active = state.get_active()
    last = state.last_reconcile()
    if active:
        short = state.short_id_for(active["clickup_id"])
        prefix = f"[{short}] " if short else ""
        click.echo(
            f"\nActive: {prefix}{active['clickup_id']} — {active.get('name', '')}"
        )
    elif last:
        click.echo(f"\nNo active task. Last list refresh: {last}")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@click.command(name="list")
@click.option("--overdue", is_flag=True, help="Show overdue tasks")
@click.option("--today", is_flag=True, help="Show tasks due today")
@click.option("--week", is_flag=True, help="Show tasks due this week")
@click.option("-n", "--limit", type=int, help="Limit results")
@click.option("--verbose", is_flag=True, help="Show extra info")
@click.option("--workspace-id", help="Override workspace ID")
@click.option("--include-closed", is_flag=True, help="Include closed tasks")
@click.option(
    "--mine",
    is_flag=True,
    default=True,
    help="Show only tasks assigned to you (default)",
)
@click.option(
    "--all", "show_all", is_flag=True, help="Show tasks for the whole workspace"
)
@click.option("--hide-subtasks", is_flag=True, help="Hide subtasks from the list")
@click.option(
    "--offline",
    is_flag=True,
    help="Use locally cached task list (no network required)",
)
@click.option(
    "--tag",
    "tags",
    multiple=True,
    help="Only tasks with this tag (repeatable; tasks must have ALL tags given)",
)
@click.option(
    "--no-tag",
    "no_tags",
    multiple=True,
    help="Exclude tasks with this tag (repeatable)",
)
@click.option(
    "--team",
    "teams",
    multiple=True,
    help=(
        "Only tasks assigned to this team (user-group) by name or id "
        "(repeatable; OR semantics). Run 'cupt teams' to list available teams."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output raw task data as JSON (pipeable, no headers or background caching)",
)
def list_tasks_cmd(
    overdue,
    today,
    week,
    limit,
    verbose,
    workspace_id=None,
    include_closed=False,
    mine=True,
    show_all=False,
    hide_subtasks=False,
    offline=False,
    tags=(),
    no_tags=(),
    teams=(),
    as_json=False,
):
    """List tasks with optional filters"""
    if show_all:
        mine = False
    return list_tasks(
        overdue,
        today,
        week,
        limit,
        verbose,
        workspace_id,
        include_closed,
        mine,
        hide_subtasks,
        offline,
        tags,
        no_tags,
        teams,
        as_json,
    )


def _filter_by_tags(tasks, tags, no_tags):
    """CLI shim — real implementation lives on TaskService."""
    return TaskService.filter_by_tags(
        tasks, required=list(tags) or None, excluded=list(no_tags) or None
    )


def list_tasks(
    overdue=False,
    today=False,
    week=False,
    limit=None,
    verbose=False,
    workspace_id=None,
    include_closed=False,
    mine=True,
    hide_subtasks=False,
    offline=False,
    tags=(),
    no_tags=(),
    teams=(),
    as_json=False,
):
    """List and display tasks."""
    config, client, config_workspace_id = get_client_context(need_workspace=False)
    if not client:
        return []

    active_workspace_id = workspace_id or config_workspace_id
    if not active_workspace_id:
        print_error(
            "Workspace ID not set. Run 'cupt config --workspace-id <id>' first."
        )
        return []

    user_id = config.get("user.user_id")

    try:
        if offline:
            return _list_tasks_offline(
                config, limit, verbose, hide_subtasks, tags, no_tags, teams, as_json
            )

        service = TaskService(client)
        team_filter_active = bool(teams)
        list_start = time.perf_counter()
        tasks = service.list_tasks(
            workspace_id=active_workspace_id,
            user_id=user_id,
            overdue=overdue,
            today=today,
            week=week,
            include_closed=include_closed,
            mine=mine,
            tags=list(tags) if tags else None,
            teams_filter=team_filter_active,
        )
        list_elapsed = time.perf_counter() - list_start

        if not tasks:
            if as_json:
                click.echo("[]")
            else:
                print_warning("No active tasks found matching criteria.")
            return []

        if hide_subtasks:
            tasks = [t for t in tasks if not t.get("parent")]

        tasks = _filter_by_tags(tasks, tags, no_tags)

        if teams:
            tasks = TaskService.filter_by_teams(tasks, required=list(teams))

        if not tasks:
            if as_json:
                click.echo("[]")
            else:
                print_warning("No tasks matched the filter.")
            return []

        if limit:
            tasks = tasks[:limit]

        if as_json:
            click.echo(json.dumps(tasks, indent=2))
            return tasks

        # Resolve parent names for subtasks (persistent cache).
        parent_cache = config.load_cache()
        for t in tasks:
            parent_cache[t["id"]] = t["name"]
        service.resolve_parent_names(active_workspace_id, tasks, parent_cache)
        config.save_cache(parent_cache)

        # Silently update task cache for --offline use.
        config.save_task_cache(
            {
                "tasks": tasks,
                "workspace_id": active_workspace_id,
                "timestamp": time.time(),
            }
        )

        # Short-ID reconciliation runs only for interactive "my pending" lists.
        # A full sync (free + assign) requires the result to actually be the
        # full pending set — filtered views (today/overdue/week) only add IDs.
        short_map = None
        state: Optional[StateManager] = None
        if is_interactive() and mine and not as_json:
            state = StateManager()
            full_sync = not (overdue or today or week)
            short_map = state.reconcile(tasks, full_sync=full_sync)

        _render_task_list(tasks, verbose, parent_cache, short_map=short_map)

        if team_filter_active:
            _print_team_filter_footer(service, list_elapsed, mine)

        if state is not None:
            _print_active_footer(state)

        # Transparently seed detail cache while the user reads the list.
        _background_cache_tasks(client, config, tasks)

        return tasks

    except Exception as e:
        print_error(f"Failed to list tasks: {e}")
        return []


def _background_cache_tasks(client, config, tasks, timeout: float = 2.0) -> int:
    """
    Fetch full task details concurrently after the list is displayed.
    Returns within `timeout` seconds, saving whatever completes.
    Any in-flight API calls that finish after the deadline are discarded.
    """
    task_ids = [t["id"] for t in tasks]
    parent_ids = list({t["parent"] for t in tasks if t.get("parent")} - set(task_ids))
    all_detail_ids = task_ids + parent_ids

    executor = ThreadPoolExecutor(max_workers=8)
    detail_futures = {
        tid: executor.submit(client.get_task, tid) for tid in all_detail_ids
    }
    comment_futures = {
        tid: executor.submit(client.get_task_comments, tid) for tid in task_ids
    }

    deadline = time.time() + timeout
    cached_count = 0
    now = time.time()

    for task_id in task_ids:
        remaining = deadline - time.time()
        if remaining <= 0:
            break

        try:
            detail = detail_futures[task_id].result(timeout=remaining)
        except Exception:
            continue  # detail failed or timed out — skip this task

        remaining = deadline - time.time()
        try:
            comments = comment_futures[task_id].result(timeout=max(0.0, remaining))
        except Exception:
            comments = []

        parent_id = detail.get("parent")
        parent = None
        if parent_id and parent_id in detail_futures:
            remaining = deadline - time.time()
            try:
                parent = detail_futures[parent_id].result(timeout=max(0.0, remaining))
            except Exception:
                pass

        config.save_task_detail(
            task_id,
            {
                "task": detail,
                "parent": parent,
                "comments": comments,
                "cached_at": now,
            },
        )
        cached_count += 1

    executor.shutdown(wait=False, cancel_futures=True)
    return cached_count


def _list_tasks_offline(
    config,
    limit,
    verbose,
    hide_subtasks,
    tags=(),
    no_tags=(),
    teams=(),
    as_json=False,
):
    """Display tasks from local cache without any API calls."""
    cached = config.load_task_cache()
    if not cached:
        if as_json:
            click.echo("[]")
        else:
            print_error("No cached data available. Run 'cupt list' while online first.")
        return []

    if not as_json:
        age_minutes = (time.time() - cached.get("timestamp", 0)) / 60
        if age_minutes > 60:
            print_warning(f"Offline cache is {int(age_minutes)} minutes old.")
        else:
            print_warning(
                f"Offline mode — showing data cached {int(age_minutes)}m ago."
            )

    tasks = cached.get("tasks", [])
    parent_cache = config.load_cache()

    if not tasks:
        if as_json:
            click.echo("[]")
        else:
            print_warning("No tasks in cache.")
        return []

    if hide_subtasks:
        tasks = [t for t in tasks if not t.get("parent")]

    tasks = _filter_by_tags(tasks, tags, no_tags)
    if teams:
        tasks = TaskService.filter_by_teams(tasks, required=list(teams))
    if not tasks:
        if as_json:
            click.echo("[]")
        else:
            print_warning("No tasks matched the filter.")
        return []

    if limit:
        tasks = tasks[:limit]

    if as_json:
        click.echo(json.dumps(tasks, indent=2))
        return tasks

    # Offline mode reuses the already-tracked short IDs (no reconciliation —
    # we have no fresh API data to know which IDs should be freed).
    short_map = None
    state: Optional[StateManager] = None
    if is_interactive():
        state = StateManager()
        short_map = state.short_id_map()

    _render_task_list(tasks, verbose, parent_cache, short_map=short_map)

    if state is not None:
        _print_active_footer(state)

    return tasks


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@click.command(name="show")
@click.argument("task_id", required=False)
@click.option("--notes", is_flag=True, help="Show task notes")
@click.option(
    "--offline",
    is_flag=True,
    help="Use cached data (no network required)",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output raw task data as JSON (always includes parent + comments)",
)
def show_task_cmd(task_id, notes, offline, as_json):
    """Show detailed task information. Falls back to the active task."""
    try:
        task_id = resolve_task_id(task_id)
    except IDResolutionError as e:
        print_error(str(e))
        return
    return show_task(task_id, notes, offline, as_json)


def show_task(
    task_id: str,
    include_notes: bool = False,
    offline: bool = False,
    as_json: bool = False,
):
    """Display full details for a single task."""
    config, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    if offline:
        return _show_task_offline(config, task_id, include_notes, as_json)

    try:
        task = client.get_task(task_id)

        if not task:
            if as_json:
                click.echo("null")
            else:
                print_error(f"Task {task_id} not found")
            return

        p_id = task.get("parent")

        def _fetch_parent():
            if not p_id:
                return None
            try:
                return client.get_task(p_id)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_parent = executor.submit(_fetch_parent)
            fut_notes = executor.submit(client.get_task_comments, task_id)

        parent_task = fut_parent.result()
        comments = fut_notes.result()

        # Always save to detail cache so --offline works next time.
        config.save_task_detail(
            task_id,
            {
                "task": task,
                "parent": parent_task,
                "comments": comments,
                "cached_at": time.time(),
            },
        )

        if as_json:
            click.echo(
                json.dumps(
                    {"task": task, "parent": parent_task, "comments": comments},
                    indent=2,
                )
            )
            return

        _display_task(task, parent_task, comments, include_notes)

    except Exception as e:
        print_error(f"Failed to show task: {e}")


def _display_task(task, parent_task, comments, include_notes: bool):
    """Render task details to stdout."""
    click.echo(f"\nTask: {task.get('name')}")
    click.echo("=" * 40)
    click.echo(f"ID:       {task.get('id')}")
    click.echo(f"Status:   {task.get('status', {}).get('status', 'unknown').upper()}")
    priority = task.get("priority")
    click.echo(
        f"Priority: {priority.get('priority', 'none').upper() if priority else 'NONE'}"
    )
    individuals = [a.get("username", "?") for a in task.get("assignees", [])]
    groups = [g.get("name", "?") for g in task.get("group_assignees", [])]
    assignees = individuals + groups
    click.echo(f"Assignee: {', '.join(assignees) if assignees else 'Unassigned'}")
    click.echo(f"Due Date: {format_date(task.get('due_date'))}")
    tag_names = [t.get("name", "") for t in (task.get("tags") or []) if t.get("name")]
    if tag_names:
        click.echo(f"Tags:     {', '.join(tag_names)}")
    attachments = task.get("attachments") or []
    if attachments:
        click.echo(
            f"Attach:   {len(attachments)} file(s) — use 'cupt attach list {task.get('id')}'"
        )
    click.echo(f"Space:    {task.get('space', {}).get('id')}")
    click.echo(
        f"Folder:   {task.get('folder', {}).get('name', 'N/A')} ({task.get('folder', {}).get('id', 'N/A')})"
    )
    click.echo(
        f"List:     {task.get('list', {}).get('name', 'N/A')} ({task.get('list', {}).get('id', 'N/A')})"
    )

    p_id = task.get("parent")
    if p_id:
        if parent_task:
            click.echo(f"Parent:   {parent_task.get('name', 'Unknown')} ({p_id})")
        else:
            click.echo(f"Parent:   {p_id}")

    desc = task.get("description", "")
    if desc:
        click.echo("\nDescription:")
        click.echo("-" * 20)
        click.echo(desc)

    if include_notes:
        click.echo("\nNotes:")
        click.echo("-" * 20)
        if not comments:
            click.echo("No notes found.")
        for msg in comments:
            author = msg.get("user", {}).get("username", "Unknown")
            text = msg.get("text", "")
            date = format_date(msg.get("date"))
            click.echo(f"[{date}] {author}: {text}")


def _show_task_offline(
    config, task_id: str, include_notes: bool, as_json: bool = False
):
    """Display task from local cache without any API calls."""
    cached = config.load_task_detail(task_id)

    if cached:
        if as_json:
            click.echo(
                json.dumps(
                    {
                        "task": cached["task"],
                        "parent": cached.get("parent"),
                        "comments": cached.get("comments", []),
                    },
                    indent=2,
                )
            )
            return
        age_minutes = (time.time() - cached.get("cached_at", 0)) / 60
        print_warning(f"Offline mode — data cached {int(age_minutes)}m ago.")
        _display_task(
            cached["task"],
            cached.get("parent"),
            cached.get("comments", []),
            include_notes,
        )
        return

    # Fallback: list cache has basic data (no description or notes)
    list_cached = config.load_task_cache()
    if list_cached:
        task = next(
            (t for t in list_cached.get("tasks", []) if t["id"] == task_id), None
        )
        if task:
            if as_json:
                click.echo(
                    json.dumps({"task": task, "parent": None, "comments": []}, indent=2)
                )
                return
            age_minutes = (time.time() - list_cached.get("timestamp", 0)) / 60
            print_warning(
                f"Partial offline data (list cache, {int(age_minutes)}m old). "
                "Run 'cupt prefetch' for full details and notes."
            )
            _display_task(task, None, [], include_notes)
            return

    if as_json:
        click.echo("null")
        return
    print_error(
        f"Task {task_id} not in offline cache. "
        "Run 'cupt prefetch' or 'cupt show <id>' online first."
    )


# ---------------------------------------------------------------------------
# prefetch
# ---------------------------------------------------------------------------


@click.command(name="prefetch")
@click.option("-n", "--limit", type=int, help="Max tasks to prefetch")
@click.option("--workspace-id", help="Override workspace ID")
def prefetch_cmd(limit, workspace_id):
    """Pre-fetch task details and notes for offline use"""
    config, client, config_workspace_id = get_client_context(need_workspace=False)
    if not client:
        return

    active_workspace_id = workspace_id or config_workspace_id
    if not active_workspace_id:
        print_error(
            "Workspace ID not set. Run 'cupt config --workspace-id <id>' first."
        )
        return

    user_id = config.get("user.user_id")

    service = TaskService(client)
    tasks = service.list_tasks(workspace_id=active_workspace_id, user_id=user_id)

    if not tasks:
        print_warning("No tasks found.")
        return

    if limit:
        tasks = tasks[:limit]

    # Update list cache while we're here.
    config.save_task_cache(
        {
            "tasks": tasks,
            "workspace_id": active_workspace_id,
            "timestamp": time.time(),
        }
    )

    click.echo(f"Prefetching details for {len(tasks)} tasks...")
    cached_count = _prefetch_details(client, config, tasks)
    print_success(f"Cached {cached_count}/{len(tasks)} tasks for offline use.")


def _prefetch_details(client, config, tasks) -> int:
    """Fetch full details + comments for each task concurrently and persist to cache."""
    task_ids = [t["id"] for t in tasks]
    # Also pre-fetch parent tasks that aren't already in our list.
    parent_ids = list({t["parent"] for t in tasks if t.get("parent")} - set(task_ids))
    all_detail_ids = task_ids + parent_ids

    with ThreadPoolExecutor(max_workers=8) as executor:
        detail_futures = {
            tid: executor.submit(client.get_task, tid) for tid in all_detail_ids
        }
        comment_futures = {
            tid: executor.submit(client.get_task_comments, tid) for tid in task_ids
        }

    details = {}
    for tid, fut in detail_futures.items():
        try:
            details[tid] = fut.result()
        except Exception:
            details[tid] = None

    cached_count = 0
    now = time.time()
    for task_id in task_ids:
        task_detail = details.get(task_id)
        if task_detail is None:
            continue

        parent_id = task_detail.get("parent")
        parent = details.get(parent_id) if parent_id else None

        try:
            comments = comment_futures[task_id].result()
        except Exception:
            comments = []

        config.save_task_detail(
            task_id,
            {
                "task": task_detail,
                "parent": parent,
                "comments": comments,
                "cached_at": now,
            },
        )
        cached_count += 1

    return cached_count


# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------


@click.command(name="done")
@click.argument("task_id", required=False)
@click.option("--note", help="Add a completion note")
@click.option(
    "--auto-note",
    is_flag=True,
    help="Use local AI (Apple Intelligence) to suggest a completion note",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help=(
        "Resolve and print the target status without modifying the task. "
        "Useful for agents to sanity-check before writing."
    ),
)
def complete_task_cmd(task_id, note, auto_note, dry_run):
    """Mark a task as complete. Falls back to the active task."""
    try:
        task_id = resolve_task_id(task_id)
    except IDResolutionError as e:
        print_error(str(e))
        return
    return complete_task(task_id, note, auto_note, dry_run)


def complete_task(
    task_id: str,
    note: Optional[str] = None,
    auto_note: bool = False,
    dry_run: bool = False,
):
    """Mark a task complete via TaskService."""
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        service = TaskService(client)

        if dry_run:
            resolved = service.resolve_completion_status(task_id)
            list_label = resolved.get("list_name") or resolved.get("list_id")
            print_success(
                f"Would mark task {task_id} as '{resolved['target']}' "
                f"(list: {list_label}). No changes made."
            )
            return

        if auto_note and not note:
            note = _get_auto_note(client, task_id)

        target_status = service.complete_task(task_id, note)
        print_success(f"Task {task_id} marked as '{target_status}'!")

        # Closing the task ends the "I'm working on this" session. Free the
        # short ID so the next reconcile slot opens up immediately, and
        # clear the active pointer only if it was this task.
        if is_interactive():
            state = StateManager()
            state.free_short_for(task_id)
            state.clear_active(only_if_id=task_id)
    except ValueError as e:
        print_error(str(e))
    except Exception as e:
        print_error(f"Failed to complete task: {e}")


# ---------------------------------------------------------------------------
# statuses
# ---------------------------------------------------------------------------


@click.command(name="statuses")
@click.argument("identifier")
@click.option(
    "--list",
    "is_list",
    is_flag=True,
    help="Treat the argument as a list ID instead of a task ID.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output raw status data as JSON, plus the resolved target.",
)
def statuses_cmd(identifier, is_list, as_json):
    """Show status names available for a task's list.

    By default the argument is a task ID and the command resolves to the
    task's list. Use --list to pass a list ID directly. The status that
    `cupt done` would apply is marked with an arrow.
    """
    return show_statuses(identifier, is_list, as_json)


def show_statuses(identifier: str, is_list: bool = False, as_json: bool = False):
    _, client, _ = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        service = TaskService(client)

        if is_list:
            list_id = identifier
            list_name: Optional[str] = None
            statuses = client.get_list_statuses(list_id)
            # Resolve the would-be target using the same rules done uses.
            target = next(
                (s["status"] for s in statuses if s.get("type") == "closed"), None
            )
            if not target:
                target = next(
                    (
                        s["status"]
                        for s in statuses
                        if s.get("status", "").lower() in TaskService._DONE_NAMES
                    ),
                    "complete",
                )
        else:
            resolved = service.resolve_completion_status(identifier)
            list_id = resolved["list_id"]
            list_name = resolved["list_name"]
            statuses = resolved["all_statuses"]
            target = resolved["target"]

        if as_json:
            import json as _json

            click.echo(
                _json.dumps(
                    {
                        "list_id": list_id,
                        "list_name": list_name,
                        "target": target,
                        "statuses": statuses,
                    },
                    indent=2,
                )
            )
            return

        if not statuses:
            print_warning(f"No statuses found for list {list_id}.")
            return

        label = f"{list_name} ({list_id})" if list_name else list_id
        click.echo(f"\nList: {label}")
        click.echo("Statuses:")
        # Widest name for alignment.
        name_w = max(len(s.get("status", "?")) for s in statuses)
        for s in statuses:
            name = s.get("status", "?")
            stype = s.get("type", "?")
            marker = "  ← cupt done resolves here" if name == target else ""
            click.echo(f"  - {name:<{name_w}}  [{stype}]{marker}")
        click.echo()

    except ValueError as e:
        print_error(str(e))
    except Exception as e:
        print_error(f"Failed to fetch statuses: {e}")


# ---------------------------------------------------------------------------
# auto-note (used by cupt done --auto-note)
# ---------------------------------------------------------------------------


def _get_auto_note(client, task_id: str) -> Optional[str]:
    """Fetch task context, call local AI for a note suggestion, prompt accept/edit/skip."""
    from cupt.ai import get_ai_suggestion

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_task = executor.submit(client.get_task, task_id)
            fut_comments = executor.submit(client.get_task_comments, task_id)
        task = fut_task.result()
        comments = fut_comments.result()
    except Exception:
        task, comments = {}, []

    parts = [f"Task: {task.get('name', task_id)}"]
    if task.get("description"):
        parts.append(f"Description: {task['description'][:400]}")
    recent = [c.get("text", "") for c in comments[-3:] if c.get("text")]
    if recent:
        parts.append("Recent notes: " + "; ".join(recent))

    prompt = (
        "Write a brief, professional one-sentence completion note for this task "
        "(just the note, no preamble):\n\n" + "\n".join(parts)
    )

    suggestion = get_ai_suggestion(prompt)

    if not suggestion:
        print_warning("No local AI available. Use --note to add a note manually.")
        return None

    click.echo(f"\nSuggested note: {suggestion}")
    choice = click.prompt("[a]ccept / [e]dit / [s]kip", default="a")

    if choice.lower().startswith("e"):
        return click.prompt("Note", default=suggestion)
    if choice.lower().startswith("s"):
        return None
    return suggestion


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------


@click.command(name="context")
@click.argument("task_id", required=False)
@click.option("--show-completed", is_flag=True, help="Include completed subtasks")
def context_cmd(task_id, show_completed):
    """Show task context (parent, siblings, subtasks). Falls back to active task."""
    try:
        task_id = resolve_task_id(task_id)
    except IDResolutionError as e:
        print_error(str(e))
        return
    return show_context(task_id, show_completed)


def show_context(task_id: str, show_completed: bool = False):
    """Display a task's parent, notes, and siblings/subtasks."""
    _, client, workspace_id = get_client_context()
    if not client:
        return

    try:
        service = TaskService(client)
        ctx = service.get_task_context(task_id, workspace_id, show_completed)
        if not ctx:
            print_error(f"Task {task_id} not found")
            return

        task = ctx["task"]
        click.echo(f"\nCONTEXT FOR TASK: {task.get('name')}")
        click.echo("=" * 60)
        click.echo(f"ID:       {task.get('id')}")
        click.echo(
            f"Status:   {task.get('status', {}).get('status', 'unknown').upper()}"
        )
        click.echo(f"Due Date: {format_date(task.get('due_date'))}")

        desc = task.get("description", "")
        if desc:
            click.echo("\nDescription:")
            click.echo("-" * 20)
            click.echo(desc)

        click.echo("\nNotes:")
        click.echo("-" * 20)
        if not ctx["notes"]:
            click.echo("No notes found.")
        for msg in ctx["notes"]:
            author = msg.get("user", {}).get("username", "Unknown")
            text = msg.get("text", "")
            click.echo(f"[{author}]: {text}")

        if ctx["is_subtask"] and ctx["parent_task"]:
            p = ctx["parent_task"]
            click.echo("\n" + "=" * 60)
            click.echo("PARENT TASK")
            click.echo("=" * 60)
            click.echo(f"Name:     {p.get('name')}")
            click.echo(f"ID:       {p.get('id')}")
            click.echo(
                f"Status:   {p.get('status', {}).get('status', 'unknown').upper()}"
            )
            if p.get("description"):
                click.echo("\nParent Description:")
                click.echo("-" * 20)
                click.echo(p.get("description"))
        else:
            click.echo("\n" + "=" * 60)
            click.echo("PARENT TASK: (Top Level Task)")
            click.echo("=" * 60)

        click.echo("\n" + "=" * 60)
        if ctx["is_subtask"]:
            click.echo(f"SIBLINGS (Subtasks of {ctx['task'].get('parent')})")
        else:
            click.echo(f"SUBTASKS (of {task_id})")
        click.echo("=" * 60)

        if not ctx["siblings"]:
            click.echo("No relevant subtasks found.")
        else:
            click.echo(f"{'ID':<12} {'Status':<12} {'Name'}")
            click.echo("-" * 60)
            for s in ctx["siblings"]:
                s_id = s.get("id")
                marker = ">> " if s_id == task_id else "   "
                click.echo(
                    f"{marker}{s_id:<9} {s.get('status', {}).get('status', 'unknown').upper():<12} {s.get('name')}"
                )
        click.echo("\n")

    except Exception as e:
        print_error(f"Failed to show context: {e}")
