"""Business logic for ClickUp task dependencies.

No printing, no Click — see AGENTS.md project map.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

from cupt.api import ClickUpClient

logger = logging.getLogger(__name__)

# Status types that count as "finished" for dependency-blocking purposes.
_DONE_TYPES = frozenset({"done", "closed"})


class DependencyService:
    def __init__(self, client: ClickUpClient):
        self.client = client

    def list_dependencies(self, task_id: str) -> Dict[str, Any]:
        """Summarize what ``task_id`` is waiting on and what it blocks.

        A task's ``dependencies`` array does carry a ``type`` field (commonly
        seen as ``1``), but ClickUp has never confirmed what it means, so it
        is intentionally ignored here. Direction is instead derived
        structurally, which is unambiguous:

          - An entry where ``entry["task_id"] == task_id`` means ``task_id``
            is *waiting on* ``entry["depends_on"]``.
          - An entry where ``entry["depends_on"] == task_id`` means
            ``task_id`` is *blocking* ``entry["task_id"]``.

        Do not branch on ``type`` anywhere in this method — see above.

        Linked tasks are resolved concurrently (capped at 10 workers), the
        way ``TaskService.resolve_parent_names`` does. A linked task that
        fails to fetch degrades to ``name=None``, ``status=None``,
        ``complete=False`` rather than failing the whole call.

        Returns:
            ``{"task_id": str, "waiting_on": [...], "blocking": [...],
               "blocked": bool}``. Each entry in ``waiting_on``/``blocking``
            is ``{"id", "name", "status", "complete"}``. ``blocked`` is True
            when any ``waiting_on`` entry is not yet complete — this is what
            lets an automated caller decide to skip the task.
        """
        task = self.client.get_task(task_id)
        deps = task.get("dependencies") or []

        task_id_str = str(task_id)
        waiting_on_ids: List[str] = []
        blocking_ids: List[str] = []
        for entry in deps:
            entry_task_id = entry.get("task_id")
            entry_depends_on = entry.get("depends_on")
            if entry_task_id is not None and str(entry_task_id) == task_id_str:
                waiting_on_ids.append(str(entry_depends_on))
            elif entry_depends_on is not None and str(entry_depends_on) == task_id_str:
                blocking_ids.append(str(entry_task_id))

        unique_ids = list(dict.fromkeys(waiting_on_ids + blocking_ids))
        resolved = self._resolve_linked_tasks(unique_ids)

        waiting_on = [resolved[dep_id] for dep_id in waiting_on_ids]
        blocking = [resolved[dep_id] for dep_id in blocking_ids]
        blocked = any(not entry["complete"] for entry in waiting_on)

        return {
            "task_id": task_id_str,
            "waiting_on": waiting_on,
            "blocking": blocking,
            "blocked": blocked,
        }

    def _resolve_linked_tasks(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch each linked task concurrently, degrading gracefully on failure."""
        if not ids:
            return {}

        def _fetch_one(dep_id: str) -> Dict[str, Any]:
            try:
                linked = self.client.get_task(dep_id)
                status = (linked.get("status") or {}).get("status")
                status_type = (linked.get("status") or {}).get("type")
                return {
                    "id": dep_id,
                    "name": linked.get("name"),
                    "status": status,
                    "complete": status_type in _DONE_TYPES,
                }
            except Exception:
                logger.debug("Could not fetch linked task %s", dep_id, exc_info=True)
                return {
                    "id": dep_id,
                    "name": None,
                    "status": None,
                    "complete": False,
                }

        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(len(ids), 10)) as executor:
            for entry in executor.map(_fetch_one, ids):
                results[entry["id"]] = entry
        return results

    def add_dependency(self, task_id: str, waiting_on: str) -> Dict[str, Any]:
        """Make ``task_id`` wait on ``waiting_on``."""
        return self.client.add_task_dependency(task_id, waiting_on)

    def remove_dependency(self, task_id: str, waiting_on: str) -> Dict[str, Any]:
        """Remove the link that makes ``task_id`` wait on ``waiting_on``."""
        return self.client.remove_task_dependency(task_id, waiting_on)
