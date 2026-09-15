# cupt v1.1 Agent Contract

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

Filters, all repeatable unless noted:

| Option | Semantics |
| ------ | --------- |
| `--tag NAME` | AND across names. |
| `--no-tag NAME` | Excluded if the task bears any. |
| `--team NAME\|ID` | OR across teams (user-groups). |
| `--status NAME` | OR. Pushed to ClickUp's server-side `statuses[]`. |
| `--list NAME` | OR, matched on the task's own `list.name`. |
| `--field NAME=VALUE` | AND across distinct names. Compared case-insensitively against the field's human-readable value. |
| `--sort NAME` | Not repeatable. Ascending by a numeric custom field; missing or non-numeric values sort last. Applied before `--limit`, so `--sort size -n 5` is the five smallest. |

`--field` splits on the first `=` only, so a value may contain `=`. A `--field`
argument with no `=` is a usage error and exits 4 rather than silently matching
nothing.

`--status` filters server-side; `--list` and `--field` are applied client-side
after pagination. cupt therefore walks deeper through the result pages whenever
one of those is active, so the 100-task page cap cannot silently hide matches.

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

### `cupt status --json`

Identity, for a caller that checks once at startup. The `id` is the identifier,
not the name: a workspace can hold several accounts for one human or bot, and
display names are neither unique nor stable. `config_home` is the profile
actually loaded (see `CUPT_HOME`), so a caller can confirm which identity it is
about to act as before it writes anything.

```json
{
  "user": {"id": 0, "username": "name", "email": "name@example.com"},
  "workspace": {"id": "workspace_id", "name": "Workspace name"},
  "config_home": "/home/you/.cupt",
  "version": "1.1.0"
}
```

Being signed out is a failure, not an empty success: `status` exits 2 and writes
nothing to stdout. (Before v1.1 it warned and exited 0.)

### `cupt field list --json`

```json
[{"id": "field_id", "name": "Size", "type": "number", "value": 3}]
```

`value` is always the human-readable form — a dropdown reports its option
*name*, a label/multi-select a list of option names, an unset field `null`.
Field and option uuids never appear in a value. A stored value matching no
current option (its option was deleted or renamed after the value was written)
also reads as `null` rather than exposing the id ClickUp still holds; the same
`null` is what `--field` sees, so such a task declines to match instead of
matching on an id nobody typed. Fields are addressed by name
everywhere in the CLI; an unknown field name or an unknown dropdown option
exits 4 and lists the valid choices rather than writing nothing and reporting
success.

### `cupt dep list --json`

```json
{
  "task_id": "task_id",
  "waiting_on": [{"id": "task_id", "name": "Other task", "status": "to do", "complete": false}],
  "blocking": [],
  "blocked": true
}
```

`blocked` is true when any `waiting_on` entry is not `complete`, which is the
field an automated caller branches on to skip a task whose blocker is unfinished.
Direction is derived structurally from each dependency record's `task_id` /
`depends_on` pair, never from its `type` field, whose encoding ClickUp does not
document.

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
