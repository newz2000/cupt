import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from cupt.api import ClickUpClient

logger = logging.getLogger(__name__)


class TaskService:
    def __init__(self, client: ClickUpClient):
        self.client = client

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def get_filters(
        self, overdue: bool = False, today: bool = False, week: bool = False
    ) -> Dict[str, Any]:
        """Build filter parameters based on options."""
        filters: Dict[str, Any] = {"subtasks": "true", "include_subtasks": "true"}

        if overdue:
            now_ms = int(datetime.now().timestamp() * 1000)
            filters["due_date_lt"] = now_ms
            filters["order_by"] = "due_date"
            filters["reverse"] = True
        elif today:
            today_start = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            filters["due_date_gt"] = int(today_start.timestamp() * 1000)
            filters["due_date_lt"] = int(
                (today_start + timedelta(days=1)).timestamp() * 1000
            )
            filters["order_by"] = "due_date"
            filters["reverse"] = False
        elif week:
            week_start = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            filters["due_date_gt"] = int(week_start.timestamp() * 1000)
            filters["due_date_lt"] = int(
                (week_start + timedelta(days=7)).timestamp() * 1000
            )
            filters["order_by"] = "due_date"
            filters["reverse"] = False

        return filters

    # ------------------------------------------------------------------
    # Task listing
    # ------------------------------------------------------------------

    def list_tasks(
        self,
        team_id: str,
        user_id: Optional[str] = None,
        overdue: bool = False,
        today: bool = False,
        week: bool = False,
        include_closed: bool = False,
        mine: bool = True,
        max_pages: int = 15,
        tags: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch and filter tasks from the API with pagination."""
        filters = self.get_filters(overdue, today, week)

        if mine and user_id:
            filters["assignees[]"] = [user_id]

        # ClickUp's tags[] is OR semantics — server returns tasks bearing ANY
        # of these tags. The caller's --tag AND requirement is then applied
        # client-side over this narrower candidate set.
        if tags:
            filters["tags[]"] = list(tags)

        all_tasks: List[Dict[str, Any]] = []
        page = 0
        limit_pages = 5 if not mine else max_pages

        while page < limit_pages:
            filters["page"] = page
            tasks = self.client.get_team_tasks(team_id, filters)

            if not tasks:
                break

            filtered = (
                tasks
                if include_closed
                else [
                    t
                    for t in tasks
                    if t.get("status", {}).get("type") not in ("done", "closed")
                ]
            )
            all_tasks.extend(filtered)

            if len(all_tasks) >= 100 or len(tasks) < 100:
                break
            page += 1

        logger.debug(
            "list_tasks: fetched %d tasks over %d page(s)", len(all_tasks), page + 1
        )
        all_tasks.sort(
            key=lambda t: (
                t.get("due_date") is None,
                int(t.get("due_date")) if t.get("due_date") else 9_999_999_999_999,
            )
        )
        return all_tasks

    @staticmethod
    def filter_by_tags(
        tasks: List[Dict[str, Any]],
        required: Optional[List[str]] = None,
        excluded: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Filter tasks by tag (case-insensitive).

        - `required`: AND — task must bear every name in this list.
        - `excluded`: OR  — task is dropped if it bears any name in this list.

        Pure function; no I/O.
        """
        if not required and not excluded:
            return tasks
        req = {t.lower() for t in (required or [])}
        exc = {t.lower() for t in (excluded or [])}

        def names(task: Dict[str, Any]) -> set:
            return {(t.get("name") or "").lower() for t in (task.get("tags") or [])}

        def keep(task: Dict[str, Any]) -> bool:
            n = names(task)
            if req and not req.issubset(n):
                return False
            if exc and n & exc:
                return False
            return True

        return [t for t in tasks if keep(t)]

    def resolve_parent_names(
        self, team_id: str, tasks: List[Dict[str, Any]], parent_cache: Dict[str, str]
    ) -> None:
        """Enrich tasks with parent names using a persistent cache and bulk/individual API fallback."""
        missing_ids = [
            t["parent"]
            for t in tasks
            if t.get("parent") and t["parent"] not in parent_cache
        ]

        if not missing_ids:
            return

        unique_missing = list(set(missing_ids))

        # Bulk fetch first (may not return all parents if they fall outside the
        # current filter view).
        try:
            for i in range(0, len(unique_missing), 100):
                for pt in self.client.get_tasks_by_ids(
                    team_id, unique_missing[i : i + 100]
                ):
                    parent_cache[pt["id"]] = pt.get("name", pt["id"])
        except Exception:
            pass

        # Individual fallback for any still-missing parents — fetched concurrently.
        still_missing = [p_id for p_id in unique_missing if p_id not in parent_cache]
        if still_missing:

            def _fetch_one(p_id):
                try:
                    pt = self.client.get_task(p_id)
                    return p_id, pt.get("name", p_id)
                except Exception:
                    return p_id, p_id

            with ThreadPoolExecutor(
                max_workers=min(len(still_missing), 10)
            ) as executor:
                for p_id, name in executor.map(_fetch_one, still_missing):
                    parent_cache[p_id] = name

    # ------------------------------------------------------------------
    # Task completion
    # ------------------------------------------------------------------

    def complete_task(self, task_id: str, note: Optional[str] = None) -> str:
        """
        Mark a task complete and optionally add a note.

        Resolves the correct "closed" status from the task's list, falling
        back to the parent space if the list carries no statuses.

        Returns:
            The status name that was applied (e.g. "Done").

        Raises:
            ValueError: If the task's list ID cannot be determined.
        """
        task = self.client.get_task(task_id)
        list_id = task.get("list", {}).get("id")

        if not list_id:
            raise ValueError(f"Could not find list for task {task_id}")

        statuses = self.client.get_list_statuses(list_id)

        if not statuses:
            space_id = task.get("space", {}).get("id")
            if space_id:
                statuses = self.client.get_space_statuses(space_id)

        # Prefer the status explicitly typed as "closed".
        target_status = next(
            (s["status"] for s in statuses if s.get("type") == "closed"), None
        )
        # Fall back to common names.
        if not target_status:
            _DONE_NAMES = {"complete", "closed", "resolved", "done"}
            target_status = next(
                (
                    s["status"]
                    for s in statuses
                    if s.get("status", "").lower() in _DONE_NAMES
                ),
                "complete",
            )

        self.client.update_task(task_id, {"status": target_status})
        if note:
            self.client.add_task_comment(task_id, note)

        return target_status

    # ------------------------------------------------------------------
    # Task context (for the `cupt context` command)
    # ------------------------------------------------------------------

    def get_task_context(
        self, task_id: str, team_id: str, show_completed: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a task with its notes, parent, and siblings/subtasks.

        After the initial get_task() call, notes, parent, and children are
        fetched concurrently via ThreadPoolExecutor(max_workers=3).
        """
        task = self.client.get_task(task_id)
        if not task:
            return None

        p_id = task.get("parent")
        target_parent = p_id if p_id else task_id
        child_params: Dict[str, Any] = {"include_subtasks": "true", "subtasks": "true"}
        if show_completed:
            child_params["include_closed"] = "true"

        # Notes, parent, and children are independent — fetch them concurrently.
        def _fetch_notes():
            return self.client.get_task_comments(task_id)

        def _fetch_parent():
            if not p_id:
                return None
            try:
                return self.client.get_task(p_id)
            except Exception:
                return None

        def _fetch_children():
            return self.client.get_task_children(team_id, target_parent, child_params)

        with ThreadPoolExecutor(max_workers=3) as executor:
            fut_notes = executor.submit(_fetch_notes)
            fut_parent = executor.submit(_fetch_parent)
            fut_children = executor.submit(_fetch_children)

        notes = fut_notes.result()
        parent_task = fut_parent.result()
        siblings = fut_children.result()

        if not show_completed:
            siblings = [
                s
                for s in siblings
                if s.get("status", {}).get("type") not in ("done", "closed")
            ]

        return {
            "task": task,
            "notes": notes,
            "parent_task": parent_task,
            "siblings": siblings,
            "is_subtask": bool(p_id),
        }
