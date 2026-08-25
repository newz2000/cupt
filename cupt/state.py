"""
Per-user local state for interactive cupt sessions.

Persists two things to ``~/.cupt/state.json`` (or ``$CUPT_HOME/state.json``):

- ``short_ids``: Taskwarrior-style stable integer IDs for "my pending" tasks.
  ``cupt list`` reconciles them so the lowest free integer is assigned to each
  newly-seen task and freed when the task leaves the pending set.
- ``active_task``: the task ``cupt start`` last set. Other commands (note,
  done, ...) fall back to it when no ID is given.

Both features are interactive-only — see ``cupt.utils.is_interactive``. Callers
that wrap cupt as a subprocess never read or write this file.
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from cupt.config import cupt_home

logger = logging.getLogger(__name__)

_STATE_VERSION = 1


class StateManager:
    """Read/write ``~/.cupt/state.json`` with atomic on-disk writes."""

    def __init__(self, state_path: Optional[Path] = None):
        if state_path is not None:
            self.state_file = state_path
        else:
            self.state_file = cupt_home() / "state.json"
        self._state: Optional[Dict[str, Any]] = None

    # -- file I/O --------------------------------------------------------

    def _ensure_parent(self) -> None:
        self.state_file.parent.mkdir(exist_ok=True, parents=True)

    def _empty(self) -> Dict[str, Any]:
        return {
            "version": _STATE_VERSION,
            "active_task": None,
            "short_ids": {},
            "last_reconcile": None,
        }

    def _load(self) -> Dict[str, Any]:
        if self._state is not None:
            return self._state
        if not self.state_file.exists():
            self._state = self._empty()
            return self._state
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
        except Exception:
            logger.warning("state.json unreadable; starting from empty")
            data = self._empty()
        if data.get("version") != _STATE_VERSION:
            logger.warning("state.json schema mismatch; ignoring")
            data = self._empty()
        # Normalize: make sure both top-level keys exist for callers.
        data.setdefault("active_task", None)
        data.setdefault("short_ids", {})
        data.setdefault("last_reconcile", None)
        self._state = data
        return self._state

    def _save(self) -> None:
        """Atomic write — tempfile + os.replace so concurrent cupt invocations
        in two terminals never see a partial file."""
        self._ensure_parent()
        fd, tmp = tempfile.mkstemp(
            dir=str(self.state_file.parent), prefix=".state.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._state, f, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.state_file)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- active task -----------------------------------------------------

    def get_active(self) -> Optional[Dict[str, Any]]:
        return self._load().get("active_task")

    def set_active(self, clickup_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Set the active task. Returns the previous active task, if any."""
        state = self._load()
        previous = state.get("active_task")
        state["active_task"] = {
            "clickup_id": clickup_id,
            "name": name,
            "started_at": _now_iso(),
        }
        self._save()
        return previous

    def clear_active(
        self, only_if_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Clear the active task. If ``only_if_id`` is given, no-op unless the
        active task matches — protects against clearing a different task that
        became active between two commands.

        Returns the cleared entry, or None if nothing was cleared.
        """
        state = self._load()
        active = state.get("active_task")
        if not active:
            return None
        if only_if_id and active.get("clickup_id") != only_if_id:
            return None
        state["active_task"] = None
        self._save()
        return active

    # -- short IDs -------------------------------------------------------

    def lookup_short(self, short_id: int) -> Optional[Dict[str, Any]]:
        """Resolve a short integer ID to its tracked entry, or None."""
        return self._load().get("short_ids", {}).get(str(short_id))

    def short_id_map(self) -> Dict[str, str]:
        """Return ``{clickup_id: short_id_string}`` for all tracked tasks."""
        return {
            entry["clickup_id"]: short
            for short, entry in self._load().get("short_ids", {}).items()
            if entry.get("clickup_id")
        }

    def short_id_for(self, clickup_id: str) -> Optional[str]:
        """Reverse lookup: ClickUp ID → short ID string, or None."""
        for short, entry in self._load().get("short_ids", {}).items():
            if entry.get("clickup_id") == clickup_id:
                return short
        return None

    def reconcile(
        self,
        pending_tasks: List[Dict[str, Any]],
        full_sync: bool = True,
    ) -> Dict[str, str]:
        """
        Update the short-ID table to reflect the pending task set.

        - ``full_sync=True``: assign new IDs AND free IDs whose tasks aren't
          in ``pending_tasks``. Use for unfiltered ``cupt list --mine``.
        - ``full_sync=False``: additive only — assign new IDs, never free.
          Use for filtered lists (today/overdue/week) where ``pending_tasks``
          is a subset of "my pending".

        Returns ``{clickup_id: short_id_as_str}`` for all tracked tasks.
        """
        state = self._load()
        short_ids: Dict[str, Dict[str, Any]] = dict(state.get("short_ids") or {})
        pending_by_id = {t["id"]: t for t in pending_tasks if t.get("id")}

        if full_sync:
            short_ids = {
                short: entry
                for short, entry in short_ids.items()
                if entry.get("clickup_id") in pending_by_id
            }

        # Refresh cached name for surviving entries so footers stay current
        # when a task was renamed in ClickUp.
        for entry in short_ids.values():
            tid = entry.get("clickup_id")
            if tid in pending_by_id:
                entry["name"] = pending_by_id[tid].get("name") or entry.get("name", "")

        existing_ids = {entry["clickup_id"] for entry in short_ids.values()}
        used = {int(s) for s in short_ids.keys()}
        next_candidate = 1
        for tid, task in pending_by_id.items():
            if tid in existing_ids:
                continue
            while next_candidate in used:
                next_candidate += 1
            short_ids[str(next_candidate)] = {
                "clickup_id": tid,
                "name": task.get("name") or "",
                "first_seen": _now_iso(),
            }
            used.add(next_candidate)
            next_candidate += 1

        state["short_ids"] = short_ids
        state["last_reconcile"] = _now_iso()
        self._save()
        return {entry["clickup_id"]: short for short, entry in short_ids.items()}

    def free_short_for(self, clickup_id: str) -> Optional[str]:
        """Remove the short ID tracking the given ClickUp task, if any.

        Called after ``cupt done`` so the next reconciliation doesn't need
        to rediscover the closed task before reclaiming its slot.
        """
        state = self._load()
        short_ids = dict(state.get("short_ids") or {})
        freed: Optional[str] = None
        for short, entry in list(short_ids.items()):
            if entry.get("clickup_id") == clickup_id:
                freed = short
                del short_ids[short]
        if freed is not None:
            state["short_ids"] = short_ids
            self._save()
        return freed

    def last_reconcile(self) -> Optional[str]:
        return self._load().get("last_reconcile")


def _now_iso() -> str:
    """UTC ISO 8601 timestamp — stable across timezones for the on-disk log."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
