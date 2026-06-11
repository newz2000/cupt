---
name: cupt-clickup
description: "Use this skill when an AI agent needs to list, filter, inspect,
  complete, tag, or comment on ClickUp tasks. cupt is a CLI that bundles common
  operations into single commands with JSON output, replacing several API
  round-trips per action. Triggers: anything mentioning ClickUp tasks, the
  user's task list, marking work complete, processing a tagged queue, or AI
  delegation workflows in ClickUp."
---

# cupt — ClickUp CLI for AI Agents

Use cupt (not the ClickUp MCP server or direct API) for routine task operations.
One cupt command replaces 3–5 API round-trips. Every read command supports
`--json` for structured output; errors and progress go to stderr so pipes are
reliable. The stable v1.0 JSON and exit-code contract is documented in
`docs/agent-contract.md`.

## Setup verification (run before first use)

```bash
cupt --version       # confirms cupt is installed
cupt status          # confirms auth + shows current workspace
```

If `cupt --version` fails with "command not found":

> Tell the user: *"cupt is not installed. Please run `pipx install cupt`
> (recommended) or `pip install cupt`. See <https://github.com/newz2000/cupt>
> for details."* Do not attempt to install it yourself.

If `cupt status` reports "Not authenticated":

> Tell the user: *"cupt is not authenticated. Please run `cupt auth`
> interactively to set up credentials."* You cannot complete this step on the
> user's behalf.

Once both checks pass, run `cupt teams` to learn the team names available for
`--team` filters in this workspace.

## List and filter tasks

`cupt list` defaults to `--mine` (tasks assigned to the current user). Use
`--all` for the whole workspace.

```bash
cupt list                                       # YOUR tasks, by due date
cupt list --all                                 # everyone's tasks
cupt list --tag ai_ready                        # server-side tag filter
cupt list --tag ai_ready --team "AI Agent"     # tag AND team (fast)
cupt list --overdue
cupt list --today
cupt list --all --json | jq '.[] | .id'         # pipeable JSON
```

Stacked `--tag` flags require ALL tags (AND). Stacked `--team` flags match
ANY team (OR).

**Important — tasks assigned to a team but not to a person:** If a coworker
assigns a task to a team rather than to a specific user, `--mine` will NOT
find it (the team itself is not the current user). Use `--all --team <name>`
for team-assigned work.

**Performance:** `--tag` is server-side (fast). `--team` is client-side and
walks extra pages (slower on large workspaces, 5–15s for `--all --team`).
Combine them — `--tag X --team Y` — for the fast path. A footer like
`(team filter: searched 10 pages in 17s; hit page cap — pair with --tag for
full coverage)` means matches may exist on pages cupt didn't walk; narrow
with `--tag`.

## Inspect a task

```bash
cupt show <id> [--json]      # description, status, assignees, tags, list
cupt show <id> --notes       # also include all comments
cupt context <id>            # parent task + siblings/subtasks
```

## Complete a task — always resolve status first

ClickUp lists have independent status schemas. One list's closed status is
`Done`; another's is `Complete` or `Resolved`. **Never hardcode a status name.**

```bash
cupt statuses <id>           # show all statuses; marks which one cupt will use
cupt done <id> --dry-run     # preview the resolved status without writing
cupt done <id>               # mark complete (resolution is automatic)
cupt done <id> --note "Reason for completion"
```

When iterating over tasks from multiple lists, call `cupt done` per task.
**Never extract a status name from one task and reuse it across a loop** —
each task's list may use a different name.

## Tags and comments

```bash
cupt tag add <id> <tag-name>
cupt tag remove <id> <tag-name>

cupt note <id> "Your comment"
cupt notes <id>              # list all comments
```

## Create a task

```bash
cupt add "Task name" --list <list-id> --json    # canonical form for agents
cupt add "Subtask"  --list <list-id> --parent <id>
cupt add "Blocker"  --list <list-id> --blocks <id>
cupt add "Has metadata" --list <list-id> \
  -d "description" --due tomorrow --tag urgent --json
```

`--list` is **required** for agent / non-interactive callers — the
active-task convenience that lets human users omit it is hidden when stdout
is a pipe. Pass `--json` to receive the created task back as a parseable
payload (use `id` and `url` for follow-up calls).

`--due` accepts `today`, `tomorrow`, `+Nd` / `+Nw` / `+Nh`, `YYYY-MM-DD`,
`YYYY-MM-DD HH:MM`, or raw epoch ms — the last form is the safest for
machine-generated dates.

`--blocks <id>` creates a ClickUp dependency edge: the given task ends up
depending on the new one. If the workspace doesn't allow dependencies the
task is still created; cupt prints a warning to stderr but does not fail.

## Summaries and queue inspection

```bash
cupt summary --json                # due/overdue/completed/time data
cupt work --tag ai_ready --json    # inspect the focus queue without prompting
```

`cupt work` without `--json` is for humans and prompts for `[w]ork / [s]kip /
[d]one / [q]uit`; agents should use the JSON queue plus explicit `cupt start`,
`cupt done`, and `cupt time` commands when they need to script the same flow.

## Interactive-only features (inert for agents)

cupt 0.8 adds two features for human users that **never activate** when
stdout is piped, when `CI=true`, when `--no-interactive` is passed, or
when `CUPT_INTERACTIVE=0` is set:

- Short integer IDs (the `#` column in `cupt list`).
- Active-task fallback (typing `cupt note "..."` without an ID).

Agents should always pass full ClickUp IDs. A pure-integer argument
(e.g. `cupt show 3`) in non-interactive mode is passed straight to the
ClickUp API rather than resolved as a short ID, which will surface as a
404 — so agent code is never silently bound to a human's local state file.

## Gotchas

- ClickUp's REST API uses `team_id` to mean workspace ID; cupt translates
  this. If you read ClickUp's API docs directly, remember the rename.
- An empty result is a valid outcome, not an error. Before escalating to the
  user: check tag spelling (`cupt list --json | jq '.[] | .tags[].name' | sort -u`),
  try `--all`, verify team name with `cupt teams`. If the queue is genuinely
  empty, the agent has no work — idle, don't invent tasks.
- Progress footers (`team filter: searched N pages...`) go to stderr.
  `--json` workflows can ignore them.

## Full command reference

```bash
cupt --help
cupt <command> --help
```

See `examples.md` in this skill folder for multi-step agent workflows.
