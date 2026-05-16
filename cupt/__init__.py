"""
CUPT — ClickUp Task Management CLI and Python library.

Use as a CLI:
    $ cupt list --tag urgent

Use as a library:
    from cupt import ClickUpClient, TaskService

    client = ClickUpClient("pk_xxxxx")              # personal API token
    service = TaskService(client)
    tasks = service.list_tasks(team_id="123", tags=["urgent"])

Public exports are intentionally limited to the API client, services, and
typed exceptions. Internal helpers (config, CLI commands, formatting) are
not part of the public API and may change between releases.
"""

from cupt.api import ClickUpClient
from cupt.exceptions import APIError, AuthError, ConfigError, CuptError
from cupt.services.note_service import NoteService
from cupt.services.task_service import TaskService
from cupt.services.time_service import TimeService

__version__ = "0.6.1"
__author__ = "Matthew Nuzum"
__email__ = "matthew@nuzum.com"

__all__ = [
    "ClickUpClient",
    "TaskService",
    "TimeService",
    "NoteService",
    "CuptError",
    "APIError",
    "AuthError",
    "ConfigError",
    "__version__",
]
