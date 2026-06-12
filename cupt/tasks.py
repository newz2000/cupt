import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import click

from cupt.context import get_client_context
from cupt.i18n import _, format_message
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
    msg = format_message(
        "(team filter: searched {pages} pages in {elapsed:.1f}s",
        pages=pages,
        elapsed=elapsed,
    )
    if pages >= page_cap:
        msg += _("; hit page cap — pair with --tag for full coverage")
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
            f"{_('ID'):<12} {_('Status'):<12} {_('Due'):<18} "
            f"{_('Assignee'):<18} {_('Est'):<8} {_('Tracked'):<8} {_('Name')}"
        )
    else:
        click.echo(
            f"\n{short_header}{_('ID'):<12} {_('Status'):<12} "
            f"{_('Due'):<18} {_('Name')}"
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
            click.echo(f"{short_cell}{task_id:<12} {status:<12} {due_date:<18} {name}")


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
            "\n"
            + format_message(
                "Active: {prefix}{task_id} — {name}",
                prefix=prefix,
                task_id=active["clickup_id"],
                name=active.get("name", ""),
            )
        )
    elif last:
        click.echo(
            "\n"
            + format_message("No active task. Last list refresh: {last}", last=last)
        )


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
            _("Workspace ID not set. Run 'cupt config --workspace-id <id>' first.")
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
                print_warning(_("No active tasks found matching criteria."))
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
                print_warning(_("No tasks matched the filter."))
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
        print_error(format_message("Failed to list tasks: {error}", error=e))
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
            print_error(
                _("No cached data available. Run 'cupt list' while online first.")
            )
        return []

    if not as_json:
        age_minutes = (time.time() - cached.get("timestamp", 0)) / 60
        if age_minutes > 60:
            print_warning(
                format_message(
                    "Offline cache is {minutes} minutes old.",
                    minutes=int(age_minutes),
                )
            )
        else:
            print_warning(
                format_message(
                    "Offline mode — showing data cached {minutes}m ago.",
                    minutes=int(age_minutes),
                )
            )

    tasks = cached.get("tasks", [])
    parent_cache = config.load_cache()

    if not tasks:
        if as_json:
            click.echo("[]")
        else:
            print_warning(_("No tasks in cache."))
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
            print_warning(_("No tasks matched the filter."))
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
    config, client, _workspace_id = get_client_context(need_workspace=False)
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
                print_error(format_message("Task {task_id} not found", task_id=task_id))
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
            fut_notes = (
                executor.submit(client.get_task_comments, task_id)
                if include_notes or as_json
                else None
            )

        parent_task = fut_parent.result()
        comments = fut_notes.result() if fut_notes is not None else []

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
        print_error(format_message("Failed to show task: {error}", error=e))


def _display_task(task, parent_task, comments, include_notes: bool):
    """Render task details to stdout."""
    click.echo(f"\n{_('Task')}: {task.get('name')}")
    click.echo("=" * 40)
    click.echo(f"{_('ID')}:       {task.get('id')}")
    click.echo(
        f"{_('Status')}:   {task.get('status', {}).get('status', 'unknown').upper()}"
    )
    priority = task.get("priority")
    click.echo(
        f"{_('Priority')}: {priority.get('priority', 'none').upper() if priority else _('NONE')}"
    )
    individuals = [a.get("username", "?") for a in task.get("assignees", [])]
    groups = [g.get("name", "?") for g in task.get("group_assignees", [])]
    assignees = individuals + groups
    click.echo(
        f"{_('Assignee')}: {', '.join(assignees) if assignees else _('Unassigned')}"
    )
    click.echo(f"{_('Due Date')}: {format_date(task.get('due_date'))}")
    tag_names = [t.get("name", "") for t in (task.get("tags") or []) if t.get("name")]
    if tag_names:
        click.echo(f"{_('Tags')}:     {', '.join(tag_names)}")
    attachments = task.get("attachments") or []
    if attachments:
        click.echo(
            format_message(
                "Attach:   {count} file(s) — use 'cupt attach list {task_id}'",
                count=len(attachments),
                task_id=task.get("id"),
            )
        )
    click.echo(f"{_('Space')}:    {task.get('space', {}).get('id')}")
    click.echo(
        f"{_('Folder')}:   {task.get('folder', {}).get('name', _('N/A'))} "
        f"({task.get('folder', {}).get('id', _('N/A'))})"
    )
    click.echo(
        f"{_('List')}:     {task.get('list', {}).get('name', _('N/A'))} "
        f"({task.get('list', {}).get('id', _('N/A'))})"
    )

    p_id = task.get("parent")
    if p_id:
        if parent_task:
            click.echo(
                f"{_('Parent')}:   {parent_task.get('name', _('Unknown'))} ({p_id})"
            )
        else:
            click.echo(f"{_('Parent')}:   {p_id}")

    desc = task.get("description", "")
    if desc:
        click.echo("\n" + _("Description") + ":")
        click.echo("-" * 20)
        click.echo(desc)

    if include_notes:
        click.echo("\n" + _("Notes") + ":")
        click.echo("-" * 20)
        if not comments:
            click.echo(_("No notes found."))
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
        print_warning(
            format_message(
                "Offline mode — data cached {minutes}m ago.",
                minutes=int(age_minutes),
            )
        )
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
                format_message(
                    "Partial offline data (list cache, {minutes}m old). "
                    "Run 'cupt prefetch' for full details and notes.",
                    minutes=int(age_minutes),
                )
            )
            _display_task(task, None, [], include_notes)
            return

    if as_json:
        click.echo("null")
        return
    print_error(
        format_message(
            "Task {task_id} not in offline cache. "
            "Run 'cupt prefetch' or 'cupt show <id>' online first.",
            task_id=task_id,
        )
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
            _("Workspace ID not set. Run 'cupt config --workspace-id <id>' first.")
        )
        return

    user_id = config.get("user.user_id")

    service = TaskService(client)
    tasks = service.list_tasks(workspace_id=active_workspace_id, user_id=user_id)

    if not tasks:
        print_warning(_("No tasks found."))
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

    click.echo(
        format_message("Prefetching details for {count} tasks...", count=len(tasks))
    )
    cached_count = _prefetch_details(client, config, tasks)
    print_success(
        format_message(
            "Cached {cached_count}/{total} tasks for offline use.",
            cached_count=cached_count,
            total=len(tasks),
        )
    )


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
    "--dry-run",
    is_flag=True,
    help=(
        "Resolve and print the target status without modifying the task. "
        "Useful for agents to sanity-check before writing."
    ),
)
def complete_task_cmd(task_id, note, dry_run):
    """Mark a task as complete. Falls back to the active task."""
    try:
        task_id = resolve_task_id(task_id)
    except IDResolutionError as e:
        print_error(str(e))
        return
    return complete_task(task_id, note, dry_run)


def complete_task(
    task_id: str,
    note: Optional[str] = None,
    dry_run: bool = False,
):
    """Mark a task complete via TaskService."""
    _config, client, _workspace_id = get_client_context(need_workspace=False)
    if not client:
        return

    try:
        service = TaskService(client)

        if dry_run:
            resolved = service.resolve_completion_status(task_id)
            list_label = resolved.get("list_name") or resolved.get("list_id")
            print_success(
                format_message(
                    "Would mark task {task_id} as '{target}' "
                    "(list: {list_label}). No changes made.",
                    task_id=task_id,
                    target=resolved["target"],
                    list_label=list_label,
                )
            )
            return

        target_status = service.complete_task(task_id, note)
        print_success(
            format_message(
                "Task {task_id} marked as '{target_status}'!",
                task_id=task_id,
                target_status=target_status,
            )
        )

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
        print_error(format_message("Failed to complete task: {error}", error=e))


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
    _config, client, _workspace_id = get_client_context(need_workspace=False)
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
            print_warning(
                format_message("No statuses found for list {list_id}.", list_id=list_id)
            )
            return

        label = f"{list_name} ({list_id})" if list_name else list_id
        click.echo(f"\n{_('List')}: {label}")
        click.echo(_("Statuses") + ":")
        # Widest name for alignment.
        name_w = max(len(s.get("status", "?")) for s in statuses)
        for s in statuses:
            name = s.get("status", "?")
            stype = s.get("type", "?")
            marker = _("  ← cupt done resolves here") if name == target else ""
            click.echo(f"  - {name:<{name_w}}  [{stype}]{marker}")
        click.echo()

    except ValueError as e:
        print_error(str(e))
    except Exception as e:
        print_error(format_message("Failed to fetch statuses: {error}", error=e))


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
    _config, client, workspace_id = get_client_context()
    if not client:
        return

    try:
        service = TaskService(client)
        ctx = service.get_task_context(task_id, workspace_id, show_completed)
        if not ctx:
            print_error(format_message("Task {task_id} not found", task_id=task_id))
            return

        task = ctx["task"]
        click.echo(f"\n{_('CONTEXT FOR TASK')}: {task.get('name')}")
        click.echo("=" * 60)
        click.echo(f"{_('ID')}:       {task.get('id')}")
        click.echo(
            f"{_('Status')}:   {task.get('status', {}).get('status', 'unknown').upper()}"
        )
        click.echo(f"{_('Due Date')}: {format_date(task.get('due_date'))}")

        desc = task.get("description", "")
        if desc:
            click.echo("\n" + _("Description") + ":")
            click.echo("-" * 20)
            click.echo(desc)

        click.echo("\n" + _("Notes") + ":")
        click.echo("-" * 20)
        if not ctx["notes"]:
            click.echo(_("No notes found."))
        for msg in ctx["notes"]:
            author = msg.get("user", {}).get("username", "Unknown")
            text = msg.get("text", "")
            click.echo(f"[{author}]: {text}")

        if ctx["is_subtask"] and ctx["parent_task"]:
            p = ctx["parent_task"]
            click.echo("\n" + "=" * 60)
            click.echo(_("PARENT TASK"))
            click.echo("=" * 60)
            click.echo(f"{_('Name')}:     {p.get('name')}")
            click.echo(f"{_('ID')}:       {p.get('id')}")
            click.echo(
                f"{_('Status')}:   {p.get('status', {}).get('status', 'unknown').upper()}"
            )
            if p.get("description"):
                click.echo("\n" + _("Parent Description") + ":")
                click.echo("-" * 20)
                click.echo(p.get("description"))
        else:
            click.echo("\n" + "=" * 60)
            click.echo(_("PARENT TASK: (Top Level Task)"))
            click.echo("=" * 60)

        click.echo("\n" + "=" * 60)
        if ctx["is_subtask"]:
            click.echo(
                format_message(
                    "SIBLINGS (Subtasks of {parent_id})",
                    parent_id=ctx["task"].get("parent"),
                )
            )
        else:
            click.echo(format_message("SUBTASKS (of {task_id})", task_id=task_id))
        click.echo("=" * 60)

        if not ctx["siblings"]:
            click.echo(_("No relevant subtasks found."))
        else:
            click.echo(f"{_('ID'):<12} {_('Status'):<12} {_('Name')}")
            click.echo("-" * 60)
            for s in ctx["siblings"]:
                s_id = s.get("id")
                marker = ">> " if s_id == task_id else "   "
                click.echo(
                    f"{marker}{s_id:<9} {s.get('status', {}).get('status', 'unknown').upper():<12} {s.get('name')}"
                )
        click.echo("\n")

    except Exception as e:
        print_error(format_message("Failed to show context: {error}", error=e))
