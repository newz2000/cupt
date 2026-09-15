"""Business logic for ClickUp task types.

ClickUp calls these "custom items" in its REST API and "task types" in its
UI; this module uses the UI's name. A task carries its type as the integer
``custom_item_id``, which is meaningless on its own — callers work with names
("milestone", "Person") and never have to learn the numbers.
"""

import logging
from typing import Any, Dict, List, Optional

from cupt.api import ClickUpClient

logger = logging.getLogger(__name__)

# The default type every workspace has. ClickUp's /custom_item endpoint
# returns only types somebody defined, so the single most common type in any
# workspace is missing from it. Synthesizing it here is what makes `cupt
# types` match the values that actually appear on tasks — without it, the 439
# ordinary tasks in a workspace have a type that cannot be named or filtered.
DEFAULT_TYPE_ID = 0
DEFAULT_TYPE_NAME = "Task"


class TypeService:
    """Resolve task types between their names and their ``custom_item_id``."""

    def __init__(self, client: ClickUpClient):
        self.client = client
        # Memoized for the life of this service, which in the CLI is one
        # command. A single invocation may both resolve a --type name and
        # name a task's type, and that should cost one call, not two. It is
        # deliberately not persisted to the config dir: the fetch is cheap,
        # and a cached copy of the workspace's type definitions would need
        # invalidating the moment someone adds a type.
        self._cache: Optional[List[Dict[str, Any]]] = None

    def list_types(self, workspace_id: str) -> List[Dict[str, Any]]:
        """Every task type in the workspace, default type first.

        Each entry is ``{"id", "name", "description"}``. The default "Task"
        type (id 0) leads the list because it is the one every workspace has
        and the one most tasks carry.
        """
        if self._cache is not None:
            return self._cache

        types = [
            {
                "id": DEFAULT_TYPE_ID,
                "name": DEFAULT_TYPE_NAME,
                "description": "Default ClickUp task",
            }
        ]
        for item in self.client.get_custom_item_types(workspace_id):
            types.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                }
            )
        self._cache = types
        return types

    def resolve_names(self, workspace_id: str, names: List[str]) -> List[int]:
        """Turn type names into the ids ClickUp's ``custom_items[]`` filter wants.

        Matching is case-insensitive with surrounding whitespace stripped,
        because the built-in types are snake_case (``form_response``) while
        workspace-defined ones are free text (``Corp Matter``).

        Raises:
            ValueError: naming the unknown type and listing the valid ones. An
                unknown name must not quietly filter to nothing — an empty
                result would read as "no tasks match" when it really means
                "you typed a type that does not exist".
        """
        available = self.list_types(workspace_id)
        by_name = {(t["name"] or "").strip().lower(): t["id"] for t in available}

        resolved = []
        for name in names:
            key = name.strip().lower()
            if key not in by_name:
                valid = ", ".join(str(t["name"]) for t in available)
                raise ValueError(f"Unknown task type '{name}'. Valid types: {valid}")
            resolved.append(by_name[key])
        return resolved

    def name_for(self, workspace_id: str, type_id: Optional[int]) -> Optional[str]:
        """The display name for a ``custom_item_id``, or None if unrecognized.

        ClickUp omits ``custom_item_id`` on some payloads; a missing value
        means the default type, not an unknown one.
        """
        if type_id is None:
            type_id = DEFAULT_TYPE_ID
        for entry in self.list_types(workspace_id):
            if entry["id"] == type_id:
                return entry["name"]
        logger.debug("task type id %r is not defined in this workspace", type_id)
        return None
