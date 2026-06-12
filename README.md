# CUPT — ClickUp Task Management CLI

CUPT stands for "ClickUP Terminal," a command-line interface for accessing your tasks in ClickUp from the terminal or via your favorite AI-based tool.

## Features
- **Task listing** with deep paging, date filters, and subtask nesting (`↳`).
- **Tag and team filters** — `cupt list --tag ai_ready --team MattTech` scopes to exactly what you're working on.
- **Hierarchical context** — `cupt context <id>` shows a task's parent and siblings.
- **Status-aware completion** — `cupt done` resolves the correct "closed" status per task's list automatically; `--dry-run` lets you preview before writing.
- **Stateful interactive UX** — `cupt list` shows a stable `#` column (1, 2, 3…) you can type instead of long ClickUp IDs. `cupt start <id>` sets a session active task so subsequent commands (`note`, `done`, `show`, `time start`) don't need an ID. Both features auto-hide when stdout is a pipe, so scripts and agents keep their stateless behavior.
- **Quick capture** — `cupt add "task name"` creates a new task in the active task's list (or your default list). `--parent this` / `--blocks this` link it to whatever you're working on.
- **Time tracking** — start/stop timers and add manual entries.
- **Notes** — quick comments and a list view per task.
- **Attachments** — list, download, and upload files on tasks.
- **Flexible auth** — OAuth or Personal API Token.
- **Offline support** — `cupt list` transparently caches what it just showed; `cupt show <id> --offline` works without a network. `cupt prefetch` populates the cache eagerly.
- **JSON output everywhere** — every read command supports `--json` for piping into `jq` or feeding an agent.
- **Agent skill bundled** — `skill/cupt-clickup/` is a portable SKILL.md that teaches Claude Code, OpenCode, Codex, and other agents how to drive cupt efficiently. See [For AI agents](#for-ai-agents) below.

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

### 4. Work through your day without retyping IDs

In an interactive terminal `cupt list` shows a `#` column with stable short IDs (1, 2, 3…) you can use anywhere a task ID is expected:

```
#    ID           Status       Due                Name
-----------------------------------------------------------------
1    868abc       open         2026-06-09 17:00   Fix login bug
2    868def       open         2026-06-10 17:00   Review onboarding doc
3    868ghi       open         —                  Reply to client
```

These numbers stay stable across sessions until the underlying task is closed (or moves out of your pending list). `cupt show 2`, `cupt note 2 "..."`, `cupt done 2` all work.

When you pick a task to focus on, mark it active:

```bash
cupt start 1                      # or `cupt start 868abc`
# every subsequent command falls back to this task when no ID is given:
cupt note "made progress on the auth flow"
cupt time start                   # optional — start a timer for it
cupt show                         # re-read the description without retyping
cupt done --note "shipping it"    # closes the task and clears active
```

`cupt active` shows the current active task; `cupt stop` clears it without closing the task (use this when you get interrupted). Every `cupt list` ends with a one-line footer reminding you what's active, so you can spot "wrong terminal" mistakes before they happen.

Mid-task you'll often realize a new task needs to exist. `cupt add` captures it without leaving the terminal:

```bash
cupt add "Migrate the legacy auth tokens"               # lands in the active task's list
cupt add "Subtask of what I'm doing" --parent this      # subtask of active
cupt add "Have to do this first" --blocks this          # active task now depends on this one
cupt add "Reply to legal" --due tomorrow --tag urgent   # with metadata
```

Pass an explicit ID instead of `this` (`--parent 868xyz` or `--parent 2`) to link to a different task. Without `--parent` or `--blocks`, the new task is a peer — no relationship — so capture stays fast when you just want to write something down.

**Hidden in scripts.** Short IDs, the active-task fallback, and the list footer all disappear when stdout is a pipe (or when `CUPT_INTERACTIVE=0` / `--no-interactive` is set). `cupt list | grep ...`, `cupt show abc --json`, and an agent calling `cupt add "..." --list <id> --json` all behave the way they did in 0.7.x — stateless and predictable.

### 5. Filter by tag and by team

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

**A note on `--team` performance.** ClickUp's API has no server-side filter for teams, so `cupt` has to walk extra pages to find matches. On big workspaces this can take 5–20 seconds for `--all --team`. After the table you'll see a footer like `(team filter: searched N pages in T.Ts)` so the cost is honest. For the fastest, most reliable results on large workspaces, pair the team filter with a discriminating tag — the tag narrows server-side before the team filter runs:

```bash
cupt list --team MattTech --tag ai_ready    # near-instant, server narrows first
```

If you see `hit page cap — pair with --tag for full coverage` in the footer, that's a hint that matches may exist on pages we didn't walk.

### 6. Mark tasks complete — safely

Different ClickUp lists carry different status names (one uses `Done`, another `Complete`, another `Resolved`). `cupt done` figures out the right one per task's list automatically. If you want to double-check before writing:

```bash
cupt statuses <task-id>           # show all statuses for the task's list,
                                  # marking the one that done would apply
cupt done <task-id> --dry-run     # preview the resolved status, no write
cupt done <task-id>               # do it
cupt done <task-id> --note "Shipped behind the AI_v2 flag"
```

### 7. Track time, take notes, attach files

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

### 8. Going offline

Every `cupt list` invocation silently caches the tasks it just showed (plus their details and comments) for offline reads. When you know you're about to lose network, run:

```bash
cupt prefetch                     # eagerly cache details for the current task set
cupt list --offline               # later, on the plane
cupt show <task-id> --offline
```

### 9. Focus with `cupt work`

When you want to work down a queue without re-running `cupt list`, use sequential focus mode:

```bash
cupt work --tag ai_ready
cupt work --today
cupt work --team MattTech --json   # inspect the queue without prompting
```

Interactive mode presents one task at a time and accepts `[w]ork`, `[s]kip`, `[d]one`, or `[q]uit`. Selecting work sets the active task and starts a timer when possible; selecting done resolves the task's completion status per list.

### 10. Pipe everything

Every read command supports `--json`:

```bash
cupt list --tag ai_ready --json | jq '.[] | .name'
cupt statuses <task-id> --json    # agent-friendly: target + all statuses
```

Shell completion snippets for bash, zsh, and fish live in `docs/shell-completion.md`. Agent JSON and exit-code contracts live in `docs/agent-contract.md`.

You now know enough to be productive. The command reference below is a quicker reminder once these basics are in muscle memory.

## Command reference

| Command | What it does |
|---|---|
| `cupt auth` / `cupt logout` / `cupt status` | Manage credentials and check current account/workspace |
| `cupt config --workspace-id <id>` | Override the default workspace |
| `cupt teams` | List ClickUp teams (user-groups) in the workspace |
| `cupt list [--overdue\|--today\|--week] [--tag X] [--no-tag X] [--team X] [--mine\|--all] [--json] [--offline]` | List tasks with stackable filters. Interactive sessions get a `#` short-ID column. |
| `cupt show [<id>] [--notes] [--json] [--offline]` | Full task details. Falls back to the active task when no ID is given. |
| `cupt context [<id>]` | Parent + sibling/subtask view. Falls back to active. |
| `cupt statuses <id> [--list] [--json]` | Show available statuses for a task's list (or pass `--list <list-id>`) |
| `cupt done [<id>] [--note "…"] [--dry-run]` | Mark complete; clears the active pointer on success. `--dry-run` previews the resolved status. |
| `cupt add "<name>" [--list X] [--parent <id\|this>] [--blocks <id\|this>] [-d "…"] [--due …] [--tag X] [--json]` | Create a new task. Defaults: active task's list, you as assignee, no link. |
| `cupt start <id>` / `cupt stop` / `cupt active` | Set / clear / show the session's active task (interactive only). |
| `cupt work [--tag X] [--team X] [--today\|--overdue\|--week] [--json]` | Sequential focus mode: work, skip, complete, or quit one task at a time. |
| `cupt summary [--all] [--json]` | Daily due/overdue/completed/time summary. |
| `cupt tag add\|remove <id> <name>` | Tag management |
| `cupt time start [<id>]` / `cupt time stop` / `cupt time add [<id>] <dur>` / `cupt time status` | Time tracking. `start` and `add` fall back to the active task. |
| `cupt note [<id>] "<text>"` / `cupt notes [<id>]` | Add or list comments; both fall back to the active task. |
| `cupt attach list\|add\|get <id> [args]` | Attachment management |
| `cupt prefetch` | Cache details for the current task set for offline use |
| Global: `--interactive` / `--no-interactive`, `--lang`, `CUPT_INTERACTIVE=1\|0`, `CUPT_LANG` | Force interactive (short IDs + active task) or stateless mode. Default: enabled when stdout is a TTY. |

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

## For AI agents

`cupt` ships a portable agent skill (`skill/cupt-clickup/`) that teaches AI
agents — Claude Code, OpenCode, Codex, and any other tool that supports the
SKILL.md convention — how to use cupt efficiently. The skill is plain
markdown with YAML frontmatter, so the same files work across agents; only
the install path differs.

Pick the line(s) that match the agent(s) you use:

```bash
# Claude Code (user-scope — available in every project)
mkdir -p ~/.claude/skills && cp -r skill/cupt-clickup ~/.claude/skills/

# Claude Code (project-scope — checked into the repo you're working in)
mkdir -p .claude/skills && cp -r skill/cupt-clickup .claude/skills/

# OpenCode (also reads from ~/.claude/skills, so the Claude install above
# works too — these are if you prefer OpenCode's native paths)
mkdir -p ~/.config/opencode/skills && cp -r skill/cupt-clickup ~/.config/opencode/skills/

# Codex (uses its own .agents path, does NOT read .claude/skills)
mkdir -p ~/.agents/skills && cp -r skill/cupt-clickup ~/.agents/skills/
```

The skill includes a pre-flight check (`cupt --version`, `cupt status`)
so agents detect a missing install or unauthenticated account and prompt
the user instead of failing silently. It does not attempt to install cupt
itself — that's a user action.

See `skill/cupt-clickup/examples.md` for the multi-step agent workflows
the skill teaches (tagged work queues, team-scoped processing, safe
multi-list completion, human handoff, empty-queue handling).

## A note on naming: workspace vs. team

ClickUp's REST API still uses "team" for what its UI now calls "Workspace," and uses "group" for what its UI calls "Team." `cupt` follows the **current UI**:

- **Workspace** = the top-level container (`cupt config --workspace-id`).
- **Team** = a user-group within a workspace (`cupt list --team`, `cupt teams`).

If you're reading ClickUp's API docs and see `team_id`, that's the workspace ID. The CLI shields you from this.

## Testing

`cupt` is built with a focus on stability and testability.

- **Coverage**: CI enforces at least 80%.
- **Tests**: unit tests use `pytest` and mocks.

```bash
pytest --cov=cupt tests/
```

## Future Roadmap

Post-1.0 experiments are tracked in `PLAN.md`, including saved views, policy ingestion, and optional AI plugin ideas.

## Project Structure
- `cupt/` — package root
- `cupt/services/` — core business logic (TaskService, TimeService, NoteService)
- `cupt/api.py` — ClickUp API client wrapper
- `cupt/main.py` — CLI entry point
- `tests/` — unit tests

## Contributions
If you or your favorite AI tool want to make improvements, please submit a pull request. Read `AGENTS.md` before starting — it captures the project's conventions, known gotchas, and quality bar. Install the pre-commit hook (`pip install pre-commit && pre-commit install`) before committing.
