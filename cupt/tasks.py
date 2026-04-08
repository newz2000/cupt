from typing import Optional

import click

from cupt.context import get_client_context
from cupt.services.task_service import TaskService
from cupt.utils import format_date, print_error, print_success, print_warning, truncate_text


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@click.command(name="list")
@click.option("--overdue", is_flag=True, help="Show overdue tasks")
@click.option("--today", is_flag=True, help="Show tasks due today")
@click.option("--week", is_flag=True, help="Show tasks due this week")
@click.option("-n", "--limit", type=int, help="Limit results")
@click.option("--verbose", is_flag=True, help="Show extra info")
@click.option("--team-id", help="Override team ID")
@click.option("--include-closed", is_flag=True, help="Include closed tasks")
@click.option("--mine", is_flag=True, default=True, help="Show only tasks assigned to you (default)")
@click.option("--all", "show_all", is_flag=True, help="Show tasks for the whole team")
@click.option("--hide-subtasks", is_flag=True, help="Hide subtasks from the list")
def list_tasks_cmd(overdue, today, week, limit, verbose, team_id=None, include_closed=False, mine=True, show_all=False, hide_subtasks=False):
    """List tasks with optional filters"""
    if show_all:
        mine = False
    return list_tasks(overdue, today, week, limit, verbose, team_id, include_closed, mine, hide_subtasks)


def list_tasks(overdue=False, today=False, week=False, limit=None, verbose=False, team_id=None, include_closed=False, mine=True, hide_subtasks=False):
    """List and display tasks."""
    config, client, config_team_id = get_client_context(need_team=False)
    if not client:
        return []

    active_team_id = team_id or config_team_id
    if not active_team_id:
        print_error("Team ID not set. Run 'cupt config --team-id <id>' first.")
        return []

    user_id = config.get("user.user_id")

    try:
        service = TaskService(client)
        tasks = service.list_tasks(
            team_id=active_team_id,
            user_id=user_id,
            overdue=overdue,
            today=today,
            week=week,
            include_closed=include_closed,
            mine=mine,
        )

        if not tasks:
            print_warning("No active tasks found matching criteria.")
            return []

        if hide_subtasks:
            tasks = [t for t in tasks if not t.get("parent")]

        if limit:
            tasks = tasks[:limit]

        # Resolve parent names for subtasks (persistent cache).
        parent_cache = config.load_cache()
        for t in tasks:
            parent_cache[t["id"]] = t["name"]
        service.resolve_parent_names(active_team_id, tasks, parent_cache)
        config.save_cache(parent_cache)

        click.echo(f"\n{'ID':<12} {'Status':<12} {'Due':<18} {'Name'}")
        click.echo("-" * 120)

        for task in tasks:
            task_id = task.get("id", "No ID")
            status = task.get("status", {}).get("status", "unknown")
            due_date = format_date(task.get("due_date"))
            name = task.get("name", "No name")
            p_id = task.get("parent")

            if p_id:
                p_name = parent_cache.get(p_id, p_id)
                name = f"↳ {name} (sub of {p_name})"

            name = truncate_text(name, 75)
            click.echo(f"{task_id:<12} {status:<12} {due_date:<18} {name}")

        return tasks

    except Exception as e:
        print_error(f"Failed to list tasks: {e}")
        return []


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

@click.command(name="show")
@click.argument("task_id")
@click.option("--notes", is_flag=True, help="Show task notes")
def show_task_cmd(task_id, notes):
    """Show detailed task information"""
    return show_task(task_id, notes)


def show_task(task_id: str, include_notes: bool = False):
    """Display full details for a single task."""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        task = client.get_task(task_id)

        if not task:
            print_error(f"Task {task_id} not found")
            return

        click.echo(f"\nTask: {task.get('name')}")
        click.echo("=" * 40)
        click.echo(f"ID:       {task.get('id')}")
        click.echo(f"Status:   {task.get('status', {}).get('status', 'unknown').upper()}")
        priority = task.get("priority")
        click.echo(f"Priority: {priority.get('priority', 'none').upper() if priority else 'NONE'}")
        click.echo(f"Due Date: {format_date(task.get('due_date'))}")
        click.echo(f"Space:    {task.get('space', {}).get('id')}")
        click.echo(f"Folder:   {task.get('folder', {}).get('name', 'N/A')} ({task.get('folder', {}).get('id', 'N/A')})")
        click.echo(f"List:     {task.get('list', {}).get('name', 'N/A')} ({task.get('list', {}).get('id', 'N/A')})")

        p_id = task.get("parent")
        if p_id:
            try:
                parent_task = client.get_task(p_id)
                click.echo(f"Parent:   {parent_task.get('name', 'Unknown')} ({p_id})")
            except Exception:
                click.echo(f"Parent:   {p_id}")

        desc = task.get("description", "")
        if desc:
            click.echo("\nDescription:")
            click.echo("-" * 20)
            click.echo(desc)

        if include_notes:
            click.echo("\nNotes:")
            click.echo("-" * 20)
            comments = client.get_task_comments(task_id)
            if not comments:
                click.echo("No notes found.")
            for msg in comments:
                author = msg.get("user", {}).get("username", "Unknown")
                text = msg.get("text", "")
                date = format_date(msg.get("date"))
                click.echo(f"[{date}] {author}: {text}")

    except Exception as e:
        print_error(f"Failed to show task: {e}")


# ---------------------------------------------------------------------------
# done
# ---------------------------------------------------------------------------

@click.command(name="done")
@click.argument("task_id")
@click.option("--note", help="Add a completion note")
def complete_task_cmd(task_id, note):
    """Mark a task as complete"""
    return complete_task(task_id, note)


def complete_task(task_id: str, note: Optional[str] = None):
    """Mark a task complete via TaskService."""
    _, client, _ = get_client_context(need_team=False)
    if not client:
        return

    try:
        service = TaskService(client)
        target_status = service.complete_task(task_id, note)
        print_success(f"Task {task_id} marked as '{target_status}'!")
    except ValueError as e:
        print_error(str(e))
    except Exception as e:
        print_error(f"Failed to complete task: {e}")


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

@click.command(name="context")
@click.argument("task_id")
@click.option("--show-completed", is_flag=True, help="Include completed subtasks")
def context_cmd(task_id, show_completed):
    """Show task context (parent, siblings, subtasks)"""
    return show_context(task_id, show_completed)


def show_context(task_id: str, show_completed: bool = False):
    """Display a task's parent, notes, and siblings/subtasks."""
    _, client, team_id = get_client_context()
    if not client:
        return

    try:
        service = TaskService(client)
        ctx = service.get_task_context(task_id, team_id, show_completed)
        if not ctx:
            print_error(f"Task {task_id} not found")
            return

        task = ctx["task"]
        click.echo(f"\nCONTEXT FOR TASK: {task.get('name')}")
        click.echo("=" * 60)
        click.echo(f"ID:       {task.get('id')}")
        click.echo(f"Status:   {task.get('status', {}).get('status', 'unknown').upper()}")
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
            click.echo(f"Status:   {p.get('status', {}).get('status', 'unknown').upper()}")
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
                click.echo(f"{marker}{s_id:<9} {s.get('status', {}).get('status', 'unknown').upper():<12} {s.get('name')}")
        click.echo("\n")

    except Exception as e:
        print_error(f"Failed to show context: {e}")
