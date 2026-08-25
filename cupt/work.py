"""Sequential focus mode for working through tasks."""

import json
from typing import Any, Dict, Iterable, List, Optional

import click

from cupt.context import get_client_context
from cupt.errors import EXIT_INVALID_INPUT, fail
from cupt.i18n import _, format_message
from cupt.services.task_service import TaskService
from cupt.services.time_service import TimeService
from cupt.state import StateManager
from cupt.tasks import _display_task
from cupt.utils import is_interactive, print_error, print_success, print_warning


def _task_name(task: Dict[str, Any]) -> str:
    return task.get("name") or task.get("id", _("Unknown task"))


def _running_timer_task_id(entry: Optional[Dict[str, Any]]) -> Optional[str]:
    """Task a running time entry belongs to, or None if it can't be told.

    ClickUp returns the task as a nested object on some time-entry payloads
    and as a flat ``task_id`` on others — `cupt summary` reads the first form
    and `cupt time status` the second — so accept either.
    """
    if not entry:
        return None
    task = entry.get("task") or {}
    return task.get("id") or entry.get("task_id")


def _switch_timer(timer: TimeService, task_id: str) -> None:
    """Point the running timer at ``task_id``, rolling over any other one.

    `get_running_timer` is workspace-scoped, so a timer left running on an
    earlier task looks the same as a timer for this one. Skipping the start
    in that case is what let the active pointer and the timer drift apart:
    the user is told the active task changed while their minutes keep
    landing on the task they moved off. Focus mode promises a single active
    task with automatic timing, so stop the stray timer and say so.
    """
    running = timer.get_running_timer()
    if running and _running_timer_task_id(running) == task_id:
        return
    if running:
        previous = _running_timer_task_id(running) or "?"
        timer.stop_timer()
        print_warning(
            format_message(
                "Stopped the timer on {previous} — now timing this task",
                previous=previous,
            )
        )
    timer.start_timer(task_id)


@click.command(name="work")
@click.option("--tag", "tags", multiple=True, help="Only tasks with this tag")
@click.option("--team", "teams", multiple=True, help="Only tasks assigned to this team")
@click.option("--today", is_flag=True, help="Only tasks due today")
@click.option("--overdue", is_flag=True, help="Only overdue tasks")
@click.option("--week", is_flag=True, help="Only tasks due this week")
@click.option("--limit", type=int, help="Maximum tasks to queue")
@click.option("--all", "show_all", is_flag=True, help="Use workspace-wide tasks")
@click.option("--json", "as_json", is_flag=True, help="Print the work queue as JSON")
def work_cmd(
    tags: Iterable[str],
    teams: Iterable[str],
    today: bool,
    overdue: bool,
    week: bool,
    limit: Optional[int],
    show_all: bool,
    as_json: bool,
) -> None:
    """Work through matching tasks one at a time."""
    work_tasks(
        tags=tuple(tags),
        teams=tuple(teams),
        today=today,
        overdue=overdue,
        week=week,
        limit=limit,
        mine=not show_all,
        as_json=as_json,
    )


def work_tasks(
    tags: Iterable[str] = (),
    teams: Iterable[str] = (),
    today: bool = False,
    overdue: bool = False,
    week: bool = False,
    limit: Optional[int] = None,
    mine: bool = True,
    as_json: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch a work queue and optionally run the interactive focus loop."""
    config, client, workspace_id = get_client_context()
    if not client:
        return []

    service = TaskService(client)
    try:
        tasks = service.list_tasks(
            workspace_id=workspace_id,
            user_id=config.get("user.user_id"),
            today=today,
            overdue=overdue,
            week=week,
            mine=mine,
            tags=list(tags) if tags else None,
            teams_filter=bool(teams),
        )
    except Exception as e:
        # Without this the APIError reached Click uncaught: a raw traceback
        # and exit 1 where the contract promises a clean message and 5.
        fail(format_message("Failed to list tasks: {error}", error=e), e)
    tasks = TaskService.filter_by_tags(tasks, required=list(tags) or None)
    tasks = TaskService.filter_by_teams(tasks, required=list(teams) or None)
    if limit:
        tasks = tasks[:limit]

    if as_json:
        click.echo(json.dumps({"tasks": tasks, "count": len(tasks)}, indent=2))
        return tasks

    if not is_interactive():
        fail(
            _("`cupt work` is interactive-only. Use `cupt work --json` for scripts."),
            code=EXIT_INVALID_INPUT,
        )

    if not tasks:
        print_warning(_("No tasks matched the work queue."))
        return []

    _run_focus_loop(client, workspace_id, tasks)
    return tasks


def _run_focus_loop(client, workspace_id: str, tasks: List[Dict[str, Any]]) -> None:
    """Prompt through a queue of tasks."""
    state = StateManager()
    timer = TimeService(client, workspace_id)
    task_service = TaskService(client)

    for index, task in enumerate(tasks, start=1):
        task_id = task["id"]
        click.echo(
            "\n"
            + format_message(
                "Task {index}/{total}: {name}",
                index=index,
                total=len(tasks),
                name=_task_name(task),
            )
        )
        click.echo("=" * 60)
        try:
            detail = client.get_task(task_id)
        except Exception:
            detail = task
        _display_task(detail, None, [], include_notes=False)

        while True:
            choice = (
                click.prompt(_("[w]ork / [s]kip / [d]one / [q]uit"), default="w")
                .strip()
                .lower()[:1]
            )
            if choice == "w":
                previous = state.set_active(task_id, _task_name(task))
                if previous and previous.get("clickup_id") != task_id:
                    print_warning(
                        format_message(
                            "Replaced active task {task_id} — {name}",
                            task_id=previous["clickup_id"],
                            name=previous.get("name", ""),
                        )
                    )
                try:
                    _switch_timer(timer, task_id)
                except Exception as exc:
                    print_warning(
                        format_message("Could not start timer: {error}", error=exc)
                    )
                print_success(
                    format_message(
                        "Active: {task_id} — {name}",
                        task_id=task_id,
                        name=_task_name(task),
                    )
                )
                break
            if choice == "s":
                print_warning(format_message("Skipped: {task_id}", task_id=task_id))
                break
            if choice == "d":
                try:
                    target = task_service.complete_task(task_id)
                    state.free_short_for(task_id)
                    state.clear_active(only_if_id=task_id)
                    try:
                        running = timer.get_running_timer()
                        if running and _running_timer_task_id(running) == task_id:
                            timer.stop_timer()
                    except Exception as exc:
                        print_warning(
                            format_message("Could not stop timer: {error}", error=exc)
                        )
                    print_success(
                        format_message(
                            "Task {task_id} marked as '{target_status}'!",
                            task_id=task_id,
                            target_status=target,
                        )
                    )
                except Exception as exc:
                    print_error(
                        format_message("Failed to complete task: {error}", error=exc)
                    )
                break
            if choice == "q":
                print_warning(_("Work session ended."))
                return
            print_warning(_("Choose w, s, d, or q."))
