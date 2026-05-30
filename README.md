# CUPT — ClickUp Task Management CLI

CUPT stands for "ClickUP Terminal," a command-line interface for accessing your tasks in ClickUp from the terminal or via your favorite AI-based tool.

## Features
- **Task listing** with deep paging, date filters, and subtask nesting (`↳`).
- **Tag and team filters** — `cupt list --tag ai_ready --team MattTech` scopes to exactly what you're working on.
- **Hierarchical context** — `cupt context <id>` shows a task's parent and siblings.
- **Status-aware completion** — `cupt done` resolves the correct "closed" status per task's list automatically; `--dry-run` lets you preview before writing.
- **Time tracking** — start/stop timers and add manual entries.
- **Notes** — quick comments and a list view per task.
- **Attachments** — list, download, and upload files on tasks.
- **Flexible auth** — OAuth or Personal API Token.
- **Offline support** — `cupt list` transparently caches what it just showed; `cupt show <id> --offline` works without a network. `cupt prefetch` populates the cache eagerly.
- **JSON output everywhere** — every read command supports `--json` for piping into `jq` or feeding an agent.

## Installation

### Recommended: from PyPI via `pipx`

```bash
pipx install cupt
pipx upgrade cupt        # later, when a new version is published
```

`pipx` installs `cupt` in an isolated environment that's available globally — same convenience as a system package, no chance of conflicting with other Python projects. If you don't have `pipx`: `brew install pipx && pipx ensurepath`, or see <https://pipx.pypa.io/stable/installation/>.

Plain `pip install cupt` works too; `pipx` is just the friendlier default for CLI tools.

### From source (for development)

```bash
git clone https://github.com/newz2000/cupt.git
cd cupt
python -m venv venv && source venv/bin/activate
pip install -e .
```

To make a local checkout available system-wide: `pipx install --force .`

## Tutorial

This walkthrough takes about five minutes and ends with you running real queries against your ClickUp workspace.

### 1. Authenticate

```bash
cupt auth
```

You'll be asked to pick OAuth or a Personal API Token. **For most users a Personal API Token is faster** — grab one from <https://app.clickup.com/settings/apps> (it starts with `pk_`) and paste it when prompted. OAuth is the right choice if you're sharing this install with a team.

After auth, `cupt` automatically picks your first workspace as the default and you're ready to go:

```bash
cupt status        # confirm: shows your username and workspace
```

### 2. List your tasks

```bash
cupt list                       # tasks assigned to you, sorted by due date
cupt list --today               # just today
cupt list --overdue             # overdue, oldest first
cupt list --week                # the next seven days
cupt list --all                 # everyone's tasks in the workspace, not just yours
cupt list -n <N> --verbose      # cap to N rows, include assignee/estimate/tracked columns
```

The default view shows ID, status, due date, and name. Every row's ID is what you'll feed into the other commands.

### 3. Drill in on one task

```bash
cupt show <task-id>             # description, status, assignees, tags, list, folder
cupt show <task-id> --notes     # also include all comments
cupt context <task-id>          # parent + siblings/subtasks
```

### 4. Filter by tag and by team

ClickUp tags (`ai_ready`, `urgent`, `waiting`, etc.) and *teams* (what ClickUp calls user-groups in its UI, e.g. `MattTech`, `AI Agent`) are how you carve a busy workspace into something workable.

```bash
cupt list --tag <tag>                       # must have this tag
cupt list --tag <tag-a> --tag <tag-b>       # must have BOTH (AND)
cupt list --no-tag <tag>                    # must NOT have this tag

cupt teams                                  # discover team names and IDs
cupt list --team <team-name>                # only tasks assigned to that team
cupt list --team <team-a> --team <team-b>   # either team (OR)

cupt list --team <team> --tag <tag> --mine  # stack filters freely
```

`--mine` is on by default. Add `--all` (or omit `--mine`) to see the whole workspace.

### 5. Mark tasks complete — safely

Different ClickUp lists carry different status names (one uses `Done`, another `Complete`, another `Resolved`). `cupt done` figures out the right one per task's list automatically. If you want to double-check before writing:

```bash
cupt statuses <task-id>           # show all statuses for the task's list,
                                  # marking the one that done would apply
cupt done <task-id> --dry-run     # preview the resolved status, no write
cupt done <task-id>               # do it
cupt done <task-id> --note "Shipped behind the AI_v2 flag"
```

### 6. Track time, take notes, attach files

```bash
cupt time start <task-id>         # start a timer
cupt time stop                    # stop the running timer
cupt time add <task-id> 1h30m     # log time after the fact

cupt note <task-id> "Talked to the client, they want the v2 layout"
cupt notes <task-id>              # list all comments

cupt attach list <task-id>
cupt attach add <task-id> <file>
cupt attach get <task-id> <selector>
```

### 7. Going offline

Every `cupt list` invocation silently caches the tasks it just showed (plus their details and comments) for offline reads. When you know you're about to lose network, run:

```bash
cupt prefetch                     # eagerly cache details for the current task set
cupt list --offline               # later, on the plane
cupt show <task-id> --offline
```

### 8. Pipe everything

Every read command supports `--json`:

```bash
cupt list --tag ai_ready --json | jq '.[] | .name'
cupt statuses <task-id> --json    # agent-friendly: target + all statuses
```

You now know enough to be productive. The command reference below is a quicker reminder once these basics are in muscle memory.

## Command reference

| Command | What it does |
|---|---|
| `cupt auth` / `cupt logout` / `cupt status` | Manage credentials and check current account/workspace |
| `cupt config --workspace-id <id>` | Override the default workspace |
| `cupt teams` | List ClickUp teams (user-groups) in the workspace |
| `cupt list [--overdue\|--today\|--week] [--tag X] [--no-tag X] [--team X] [--mine\|--all] [--json] [--offline]` | List tasks with stackable filters |
| `cupt show <id> [--notes] [--json] [--offline]` | Full task details |
| `cupt context <id>` | Parent + sibling/subtask view |
| `cupt statuses <id> [--list] [--json]` | Show available statuses for a task's list (or pass `--list <list-id>`) |
| `cupt done <id> [--note "…"] [--auto-note] [--dry-run]` | Mark complete; `--dry-run` previews; `--auto-note` uses a local AI to draft a note |
| `cupt tag add\|remove <id> <name>` | Tag management |
| `cupt time start <id>` / `cupt time stop` / `cupt time add <id> <dur>` / `cupt time status` | Time tracking |
| `cupt note <id> "<text>"` / `cupt notes <id>` | Add or list comments |
| `cupt attach list\|add\|get <id> [args]` | Attachment management |
| `cupt prefetch` | Cache details for the current task set for offline use |

## Use as a Python library

`cupt` is usable as a dependency in your own Python code. Importing it does no I/O — no config directory is created, no network calls happen until you make one explicitly.

```python
from cupt import ClickUpClient, TaskService, APIError

client = ClickUpClient("pk_xxxxxxxxxxxxxxxx")     # personal API token
service = TaskService(client)

try:
    tasks = service.list_tasks(
        workspace_id="123456",
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

For agents that need to mark tasks complete across lists with diverging status names, use `TaskService.resolve_completion_status(task_id)` to discover the target status before writing. See `AGENTS.md` for the canonical pattern.

Public API surface (anything importable from `cupt` top-level):

| Symbol            | Purpose                                                  |
| ----------------- | -------------------------------------------------------- |
| `ClickUpClient`   | Thin HTTP wrapper around the ClickUp v2 REST API.        |
| `TaskService`     | List/filter/complete tasks; resolve parent names; resolve closed-status per list. |
| `TimeService`     | Start/stop timers, add time entries, fetch totals.       |
| `NoteService`     | Add and list task comments.                              |
| `CuptError`       | Base exception. All `cupt` errors subclass this.         |
| `APIError`        | HTTP failure, timeout, or invalid JSON from ClickUp.     |
| `AuthError`       | Missing or invalid credentials.                          |
| `ConfigError`     | Configuration is missing or malformed.                   |

Other modules (`cupt.config`, `cupt.context`, command modules) are internal to the CLI and may change between releases.

## A note on naming: workspace vs. team

ClickUp's REST API still uses "team" for what its UI now calls "Workspace," and uses "group" for what its UI calls "Team." `cupt` follows the **current UI**:

- **Workspace** = the top-level container (`cupt config --workspace-id`).
- **Team** = a user-group within a workspace (`cupt list --team`, `cupt teams`).

If you're reading ClickUp's API docs and see `team_id`, that's the workspace ID. The CLI shields you from this.

## Testing

`cupt` is built with a focus on stability and testability.

- **Coverage**: 86%
- **Tests**: 219 unit tests using `pytest` and mocks, ~0.4s wall time.

```bash
pytest --cov=cupt tests/
```

## Future Roadmap
Planned features for upcoming releases:
- **`cupt work` / `cupt gtd`**: Sequential "focused work" mode to tackle a list of tasks one by one.
- **Quick Create**: Rapidly create follow-up tasks or subtasks while you work.
- **Workflow State**: Persistent session state for long-running workflows.
- **Shell Completion**: Tab-completion for task IDs and commands.
- **Local AI integration**: Optional Ollama/Apple Intelligence/Windows Copilot backends for natural-language summaries and note suggestions.
- **Policy ingestion**: Pull guidance documents from ClickUp lists/folders so agents follow the right rules per area.

See `PLAN.md` for the full roadmap.

## Project Structure
- `cupt/` — package root
- `cupt/services/` — core business logic (TaskService, TimeService, NoteService)
- `cupt/api.py` — ClickUp API client wrapper
- `cupt/main.py` — CLI entry point
- `tests/` — unit tests

## Contributions
If you or your favorite AI tool want to make improvements, please submit a pull request. Read `AGENTS.md` before starting — it captures the project's conventions, known gotchas, and quality bar. Install the pre-commit hook (`pip install pre-commit && pre-commit install`) before committing.
