import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import click

from cupt.context import get_client_context
from cupt.errors import fail
from cupt.i18n import _, format_message
from cupt.services.task_service import TaskService
from cupt.utils import (
    format_date,
    format_duration,
    get_terminal_width,
    truncate_text,
)

# "  {id:<12} {status:<14} {name}"           -> 2+12+1+14+1 = 30 fixed cols
# "  {id:<12} {status:<14} {due:<18} {name}" -> 2+12+1+14+1+18+1 = 49 fixed
_SUMMARY_FIXED_WIDTH = 30
_SUMMARY_FIXED_WIDTH_WITH_DATE = 49


def _task_count(count: int) -> str:
    template = "{count} task" if count == 1 else "{count} tasks"
    return format_message(template, count=count)


@click.command(name="summary")
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    help="Show workspace-wide summary instead of just your tasks",
)
@click.option("--json", "as_json", is_flag=True, help="Output summary data as JSON")
def summary_cmd(show_all: bool, as_json: bool) -> None:
    """Show a daily summary: due today, overdue, completed, and time tracked."""
    show_summary(mine=not show_all, as_json=as_json)


def show_summary(mine: bool = True, as_json: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch and display a daily task and time summary."""
    config, client, workspace_id = get_client_context()
    if not client:
        return None

    user_id = config.get("user.user_id") if mine else None

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_ms = int(today.timestamp() * 1000)
    tomorrow_ms = int((today + timedelta(days=1)).timestamp() * 1000)

    task_service = TaskService(client)

    def _fetch_due_today():
        return task_service.list_tasks(
            workspace_id, user_id=user_id, today=True, mine=mine
        )

    def _fetch_overdue():
        return task_service.list_tasks(
            workspace_id, user_id=user_id, overdue=True, mine=mine
        )

    def _fetch_completed_today():
        params: Dict[str, Any] = {
            "include_closed": "true",
            "date_updated_gt": today_ms,
            "subtasks": "true",
            "include_subtasks": "true",
        }
        if mine and user_id:
            params["assignees[]"] = [user_id]
        tasks = client.get_workspace_tasks(workspace_id, params)
        return [
            t for t in tasks if t.get("status", {}).get("type") in ("done", "closed")
        ]

    def _fetch_time_entries():
        try:
            return client.get_time_entries(
                workspace_id, today_ms, tomorrow_ms, user_id=user_id
            )
        except Exception:
            return []

    def _fetch_running_timer():
        return client.get_running_timer(workspace_id)

    try:
        with ThreadPoolExecutor(max_workers=5) as executor:
            fut_due = executor.submit(_fetch_due_today)
            fut_overdue = executor.submit(_fetch_overdue)
            fut_completed = executor.submit(_fetch_completed_today)
            fut_entries = executor.submit(_fetch_time_entries)
            fut_timer = executor.submit(_fetch_running_timer)

            due_today = fut_due.result()
            overdue = fut_overdue.result()
            completed_today = fut_completed.result()
            time_entries = fut_entries.result()
            running_timer = fut_timer.result()

    except Exception as e:
        fail(format_message("Failed to fetch summary data: {error}", error=e), e)

    total_ms = sum(int(e.get("duration", 0)) for e in time_entries)
    payload: Dict[str, Any] = {
        "scope": "mine" if mine else "all",
        "date": today.date().isoformat(),
        "time_tracked_ms": total_ms,
        "running_timer": running_timer,
        "due_today": due_today,
        "overdue": overdue,
        "completed_today": completed_today,
        "time_entries": time_entries,
    }

    if as_json:
        click.echo(json.dumps(payload, indent=2))
        return payload

    _render_summary(payload)
    return payload


def _render_summary(payload: Dict[str, Any]) -> None:
    """Render summary data for humans."""
    day_label = datetime.now().strftime("%A, %B %-d, %Y")
    scope = _("Your") if payload["scope"] == "mine" else _("Workspace")
    click.echo(f"\n{scope.upper()} {_('SUMMARY')}  —  {day_label}")
    click.echo("=" * 60)

    running_timer = payload["running_timer"]
    due_today = payload["due_today"]
    overdue = payload["overdue"]
    completed_today = payload["completed_today"]

    click.echo("\n" + _("TIME TRACKED TODAY"))
    click.echo("-" * 20)
    total_ms = payload["time_tracked_ms"]
    click.echo(f"  {_('Total')}:   {format_duration(total_ms) if total_ms else '0m'}")
    if running_timer:
        start_ms = int(running_timer.get("start", 0))
        elapsed_ms = (
            int(datetime.now().timestamp() * 1000) - start_ms if start_ms else 0
        )
        task_obj = running_timer.get("task") or {}
        timer_name = task_obj.get("name") or running_timer.get(
            "task_id", _("Unknown task")
        )
        click.echo(
            format_message(
                "  Running: {timer_name} (started {elapsed} ago)",
                timer_name=timer_name,
                elapsed=format_duration(elapsed_ms),
            )
        )
    else:
        click.echo(_("  Running: none"))

    click.echo(
        "\n"
        + format_message(
            "DUE TODAY  ({task_count})",
            task_count=_task_count(len(due_today)),
        )
    )
    click.echo("-" * 20)
    if not due_today:
        click.echo(_("  Nothing due today."))
    else:
        for t in due_today:
            _print_task_line(t)

    click.echo(
        "\n"
        + format_message(
            "OVERDUE  ({task_count})", task_count=_task_count(len(overdue))
        )
    )
    click.echo("-" * 20)
    if not overdue:
        click.echo(_("  Nothing overdue."))
    else:
        for t in overdue:
            _print_task_line(t, show_date=True)

    click.echo(
        "\n"
        + format_message(
            "COMPLETED TODAY  ({task_count})",
            task_count=_task_count(len(completed_today)),
        )
    )
    click.echo("-" * 20)
    if not completed_today:
        click.echo(_("  Nothing completed today."))
    else:
        for t in completed_today:
            _print_task_line(t)

    click.echo()


def _print_task_line(task: Dict[str, Any], show_date: bool = False) -> None:
    task_id = task.get("id", "")
    status = task.get("status", {}).get("status", "unknown").upper()
    name = task.get("name", _("No name"))

    width = get_terminal_width()
    if width is None:
        name_width: Optional[int] = None
    else:
        fixed = _SUMMARY_FIXED_WIDTH_WITH_DATE if show_date else _SUMMARY_FIXED_WIDTH
        name_width = max(10, width - fixed)
    name = truncate_text(name, name_width)

    if show_date:
        due = format_date(task.get("due_date"))
        click.echo(f"  {task_id:<12} {status:<14} {due:<18} {name}")
    else:
        click.echo(f"  {task_id:<12} {status:<14} {name}")
