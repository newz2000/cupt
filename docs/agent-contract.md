# cupt v1.0 Agent Contract

This document is the stable scripting contract for agents and other automation.
It covers stdout/stderr discipline, exit codes, non-interactive behavior, and the
JSON shapes for read commands.

## Output discipline

- stdout is data.
- stderr is diagnostics, warnings, progress, and success decoration.
- Commands that support `--json` print only JSON to stdout on success.

## Exit codes

| Code | Meaning |
| ---: | ------- |
| 0 | Success. |
| 1 | Generic failure. |
| 2 | Authentication or missing workspace/configuration failure. |
| 3 | Requested object or short ID was not found. |
| 4 | Invalid user input or validation failure. |
| 5 | ClickUp API or network failure. |

Every code in this table is asserted by `tests/test_exit_codes.py`. Two notes:

- Click emits its own exit code 2 for usage errors (unknown flag, missing
  argument). It overlaps code 2 here; both mean "cannot proceed as asked", and
  the stderr message distinguishes them.
- A failure never writes to stdout, so `cupt list --json | jq` on a dead token
  yields nothing *and* a non-zero status rather than silently empty success.
- Closing the read end of the pipe early (`| head`) is not a failure. cupt uses
  the default SIGPIPE disposition, so it dies quietly like any other filter
  instead of reporting an API error.

## Non-interactive mode

Set `CUPT_INTERACTIVE=0` or pass `--no-interactive` to disable stateful UX:
short-ID resolution, active-task fallback, and prompts. Commands that require a
prompt fail cleanly instead of blocking.

`active`, `tags`, and `time status` have no `--json`: they report interactive
session state rather than ClickUp data. `cupt active` exits 0 and prints nothing
in a non-interactive session, so it is safe as a probe.

## JSON schemas

Schemas below are intentionally permissive for ClickUp-owned task fields: cupt
preserves ClickUp objects unless noted.

### `cupt list --json`

```json
[{"id": "task_id", "name": "Task name", "status": {"status": "open", "type": "open"}}]
```

### `cupt show --json`

```json
{"task": {}, "parent": null, "comments": []}
```

### `cupt context --json`

```json
{"task": {}, "notes": [], "parent_task": null, "siblings": [], "is_subtask": false}
```

`siblings` excludes completed tasks unless `--show-completed` is passed.

### `cupt notes --json`

```json
{"task_id": "task_id", "notes": []}
```

An empty `notes` array is a successful result, not a warning.

### `cupt statuses --json`

```json
{"list_id": "list_id", "list_name": "List name", "target": "Done", "statuses": []}
```

### `cupt teams --json`

```json
[{"id": "team_id", "name": "Team name", "members": []}]
```

### `cupt summary --json`

```json
{
  "scope": "mine",
  "date": "YYYY-MM-DD",
  "time_tracked_ms": 0,
  "running_timer": null,
  "due_today": [],
  "overdue": [],
  "completed_today": [],
  "time_entries": []
}
```

### `cupt add --json`

The created task, passed through from ClickUp unchanged. `id` and `name` are
always present; everything else is whatever ClickUp returns for a new task.

```json
{"id": "task_id", "name": "Task name"}
```

### `cupt work --json`

`cupt work` is interactive by default. With `--json`, it prints the candidate
queue and exits without prompting:

```json
{"tasks": [], "count": 0}
```
