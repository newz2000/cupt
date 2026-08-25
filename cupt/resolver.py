"""
Resolve user-supplied task identifiers to ClickUp task IDs.

Three input shapes feed into one output:

- Alphanumeric (e.g. ``868abc123``) → ClickUp ID, passthrough.
- Pure digits (e.g. ``3``) → short ID, looked up in state.json (interactive
  only). Non-interactive sessions pass the digits through unchanged so the
  resulting API error is loud and obvious rather than silently wrong.
- ``None`` / empty → the active task (interactive only).

Errors carry user-actionable text (run ``cupt list``, pass an ID, ...).
"""

import re
from typing import Optional

from cupt.state import StateManager
from cupt.utils import is_interactive

_SHORT_ID_RE = re.compile(r"^\d+$")


class IDResolutionError(ValueError):
    """Raised when a task identifier can't be resolved to a ClickUp ID.

    ``not_found`` separates "you named something that doesn't exist" (exit 3)
    from "you didn't give me enough to work with" (exit 4).
    """

    def __init__(self, message: str, not_found: bool = False):
        super().__init__(message)
        self.not_found = not_found


def resolve_task_id(
    arg: Optional[str],
    state: Optional[StateManager] = None,
    allow_active: bool = True,
) -> str:
    """Resolve ``arg`` (or the active task) to a ClickUp task ID.

    ``allow_active=False`` for commands like ``cupt start`` where falling back
    to the active task makes no sense — you must name the task you want.
    """
    interactive = is_interactive()
    state = state if state is not None else StateManager()

    if not arg:
        if not interactive:
            raise IDResolutionError(
                "Task ID required (non-interactive mode has no active task)."
            )
        if not allow_active:
            raise IDResolutionError("Task ID required.")
        active = state.get_active()
        if not active:
            raise IDResolutionError(
                "No task ID and no active task. Use `cupt start <id>` or pass an ID."
            )
        return active["clickup_id"]

    if _SHORT_ID_RE.match(arg):
        if not interactive:
            # In scripts a pure-int task ID would only make sense if ClickUp
            # itself used numeric IDs (it doesn't). Passing it through means
            # the failure surfaces at the API call rather than silently
            # resolving to whatever short ID the user happened to have set.
            return arg
        entry = state.lookup_short(int(arg))
        if entry is None:
            raise IDResolutionError(
                f"No short ID {arg} — run `cupt list` to refresh, "
                "or pass the full ClickUp task ID.",
                not_found=True,
            )
        return entry["clickup_id"]

    return arg
