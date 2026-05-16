# CUPT - ClickUp Task Management CLI

A powerful, modular CLI tool for managing ClickUp tasks directly from your terminal.

## Features
- **Task Listing**: View active, overdue, and upcoming tasks with deep paging support.
- **Subtask Support**: Visual nesting (`↳`) and parent task resolution.
- **Hierarchical Context**: `cupt context <id>` shows parents and sibling subtasks.
- **Time Tracking**: Start/stop timers and add manual time entries.
- **Note Management**: Quick comments and note listing.
- **Flexible Auth**: Supports both OAuth and Personal API Tokens.

## Installation

### Recommended: System-wide using `pipx`
MacOS (Homebrew) prevents installing packages directly into the system Python. Use `pipx` to install `cupt` in an isolated environment that is globally available:

```bash
# From the project root
pipx install .

# To update an existing installation after code changes:
pipx install --force .
```

If you don't have `pipx`, install it via Homebrew: `brew install pipx && pipx ensurepath`.

### Development: Local Editable Install
If you are developing or want an isolated virtual environment:
```bash
git clone https://github.com/matthewnuzum/cupt.git
cd cupt
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Configuration
```bash
cupt auth
# Follow prompts to authenticate
```

## Usage
- `cupt list`: List your active tasks
- `cupt list --overdue`: Show overdue tasks
- `cupt list --tag urgent --no-tag waiting`: Filter by tag (server-side)
- `cupt list --json`: Pipeable JSON output (combines with all filters)
- `cupt show <id>`: Show task details
- `cupt context <id>`: Show task parent and siblings
- `cupt done <id>`: Mark task as complete
- `cupt tag add <id> <name>` / `cupt tag remove <id> <name>`: Manage tags
- `cupt attach list <id>` / `cupt attach get <id> <selector>` / `cupt attach add <id> <file>`: Manage attachments
- `cupt time start <id>` / `cupt time stop`: Timer control
- `cupt note <id> "Your message"`: Add a note

## Use as a Python library

`cupt` is usable as a dependency in your own Python code. Importing it
does no I/O — no config directory is created, no network calls happen
until you make one explicitly.

```python
from cupt import ClickUpClient, TaskService, APIError

client = ClickUpClient("pk_xxxxxxxxxxxxxxxx")     # personal API token
service = TaskService(client)

try:
    tasks = service.list_tasks(
        team_id="123456",
        tags=["urgent"],          # server-side filter
        include_closed=False,
    )
    urgent_billing = service.filter_by_tags(
        tasks, required=["urgent", "billing"]
    )
    for t in urgent_billing:
        print(t["id"], t["name"])
except APIError as e:
    print(f"ClickUp request failed: {e}")
```

Public API surface (anything importable from `cupt` top-level):

| Symbol            | Purpose                                                  |
| ----------------- | -------------------------------------------------------- |
| `ClickUpClient`   | Thin HTTP wrapper around the ClickUp v2 REST API.        |
| `TaskService`     | List/filter/complete tasks; resolve parent names.        |
| `TimeService`     | Start/stop timers, add time entries, fetch totals.       |
| `NoteService`     | Add and list task comments.                              |
| `CuptError`       | Base exception. All `cupt` errors subclass this.         |
| `APIError`        | HTTP failure, timeout, or invalid JSON from ClickUp.     |
| `AuthError`       | Missing or invalid credentials.                          |
| `ConfigError`     | Configuration is missing or malformed.                   |

Other modules (`cupt.config`, `cupt.context`, command modules) are
internal to the CLI and may change between releases.

## Testing
`cupt` is built with a strong focus on stability and testability.
- **Coverage**: 75% total coverage
- **Tests**: 47 unit tests using `pytest` and mocks.

Run the test suite:
```bash
pytest --cov=cupt tests/
```

## Future Roadmap
Exciting features planned for upcoming releases:
- **`cupt work` / `cupt gtd`**: Sequential "focused work" mode to tackle a list of tasks one by one.
- **Quick Create**: Rapidly create follow-up tasks or subtasks while you work.
- **Workflow State**: Persistent session state for long-running workflows.
- **Shell Completion**: Tab-completion for task IDs and commands.

## Project Structure
- `cupt/`: Package root.
- `cupt/services/`: Core business logic (TaskService, TimeService, NoteService).
- `cupt/api.py`: ClickUp API client wrapper.
- `cupt/main.py`: CLI entry point.
- `tests/`: Comprehensive unit tests.