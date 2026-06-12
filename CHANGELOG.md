# Changelog

All notable changes to `cupt` are recorded here. Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entry style: each release lists user-visible changes grouped under
**Added** (new features), **Changed** (behavior changes), **Fixed**
(bug fixes), and **Removed** (deletions). Internal refactors with no
user impact are not listed.

## [Unreleased]

### Changed
- Documented local real-workspace performance verification and corrected
  `--all --team` timing guidance.

## [1.0.0] — 2026-06-11

### Added
- `cupt work` sequential focus mode for walking a filtered queue with work, skip, done, and quit actions.
- `cupt summary --json` for agent-readable daily summary data.
- v1.0 agent contract and deprecation policy docs.
- GitHub Actions CI for Ruff, tests with coverage, non-interactive contract checks, translation catalog checks, and package builds.
- gettext/Babel-compatible i18n scaffold with `--lang`, `CUPT_LANG`, a source catalog, and a Spanish proof-of-concept catalog.

### Changed
- Development tooling now exposes a `dev` extra for CI/test dependencies.

### Removed
- Removed `cupt done --auto-note` and the local Apple Intelligence helper so v1.0 does not freeze an unsupported AI-note contract.

## [0.8.0] — 2026-06-09

### Added
- **Short IDs in interactive sessions.** `cupt list` now prints a `#`
  column with Taskwarrior-style stable integers (1, 2, 3…) for each
  "my pending" task. Any command that takes a task ID accepts the
  short form: `cupt show 3`, `cupt note 3 "..."`, `cupt done 3`.
  Numbers are reconciled on each unfiltered list (filtered lists
  like `--today` are additive only) and freed when a task is closed.
- **Active task pointer.** `cupt start <id>` marks a task as active
  for the session; `cupt note`, `cupt done`, `cupt show`, `cupt
  context`, `cupt notes`, and `cupt time start` / `time add` fall
  back to it when no ID is given. `cupt done` clears it on success;
  `cupt stop` clears it without closing the task. `cupt active`
  shows the current pointer.
- **`--interactive` / `--no-interactive` global flag** and
  `CUPT_INTERACTIVE=1|0` env var to force the mode (default: enabled
  when stdout is a TTY).

### Changed
- Both stateful features are hidden in non-interactive use (piped
  output, `CI=true`, `--no-interactive`). Scripts always get the
  classic stateless behavior — short IDs and the active pointer are
  never consulted, and pure-integer args pass through to the API
  rather than silently resolving to a short ID.
- `cupt note` now accepts a single positional argument (the note
  text) when an active task is set. The two-arg form
  (`cupt note <id> <text>`) still works.

### Added (capture)
- **`cupt add "task name"`** — low-friction quick capture during
  work. Defaults in interactive sessions: list inferred from the
  active task (falls back to `user.default_list_id`), assignee is
  you, no relationship to anything else.
- `--blocks <id|short-id|this>` and `--parent <id|short-id|this>`
  flags. The `this` sentinel resolves to the active task; an
  explicit ID (or short ID like `3`) links to that task. `--blocks`
  uses ClickUp's dependency API; the create still succeeds even if
  the dependency call fails (e.g. workspace doesn't have
  dependencies enabled) — a warning is printed.
- `--description`, `--due`, `--tag` (repeatable), `--json`. Due-date
  accepts `today`, `tomorrow`, `+Nd` / `+Nw` / `+Nh`, `YYYY-MM-DD`,
  `YYYY-MM-DD HH:MM`, or raw epoch ms (so agent callers can pass
  timestamps without formatting).
- `ClickUpClient.create_task(list_id, data)` and
  `ClickUpClient.add_task_dependency(task_id, depends_on)` library
  methods.

## [0.7.1] — 2026-05-30

### Changed
- **`cupt list --team` now walks all available pages** instead of
  stopping at the 100-task early-exit. ClickUp's API has no
  server-side filter for team (user-group) assignments, so the
  previous behavior silently truncated matches that lived on later
  pages. Benchmarks against a real workspace showed `--all --team`
  was undercounting by up to 22× for some teams. The `--mine --team`
  path is also affected, but typically finds nothing new because
  the assignee filter already narrows server-side.
- The `--all` page cap is bumped from 5 to 10 when a team filter is
  active, giving the worst case more headroom. Worst-case latency
  is now ~15–20s on a large workspace; pair `--team` with a `--tag`
  to keep things snappy.

### Added
- `cupt list --team` prints a quiet stderr footer showing pages
  walked and wall time (e.g. `(team filter: searched 5 pages in
  8.5s)`). When the page cap is hit, the footer adds a hint
  suggesting `--tag` for full coverage.
- `TaskService.list_tasks(..., teams_filter=True)` library parameter
  exposes the same behavior to library callers.
- `TaskService.last_pages_walked` instrumentation attribute for
  callers that want to report search cost.

### Docs
- README tutorial now calls out the `--team` + `--tag` pattern as
  the fast path for large workspaces, and explains the footer.
- New `skill/cupt-clickup/` agent skill — portable SKILL.md + examples
  for AI agents (Claude Code, OpenCode, Codex, etc.) that need to use
  cupt as a token-efficient alternative to the ClickUp MCP server or
  raw REST API. Includes a self-check that prompts the user to install
  or authenticate cupt rather than failing silently. README documents
  per-agent install paths.

## [0.7.0] — 2026-05-30

### Added
- `cupt list --team <name|id>` filter — scope the list to tasks
  assigned to a ClickUp **team** (user-group; e.g. `MattTech`,
  `AI Agent`). Repeatable; OR semantics. Stacks with `--tag`,
  `--no-tag`, `--mine`/`--all`, and the date filters.
- `cupt teams` command — discovery for the IDs and names of teams
  in the current workspace.
- `cupt statuses <task-id>` (or `--list <list-id>`) — print all
  statuses available for a task's list and mark the one `cupt done`
  would apply. Supports `--json` for agent consumption.
- `cupt done --dry-run` — resolve and print the target status
  without mutating the task. Lets agents confirm "which status name
  exists in this list" before writing.
- `TaskService.resolve_completion_status(task_id)` — pure helper
  that returns `{"target", "list_id", "list_name", "all_statuses"}`
  with no side effects. Canonical entry point for any caller (CLI
  or library) that needs to know "what does done mean for this
  task's list".
- `ClickUpClient.get_teams(workspace_id)` and
  `TaskService.filter_by_teams(tasks, required=)` library APIs.
- Legacy config fallback: `user.team_id` written by pre-0.7 installs
  is still read transparently as the workspace ID, so existing users
  don't need to re-run `cupt auth` after upgrading.

### Changed (BREAKING — pre-1.0 rename to match ClickUp's current UI)
ClickUp historically called workspaces "teams" and user-groups
"groups"; the current UI uses **Workspace** and **Team** respectively.
`cupt`'s names now match the UI. Underlying REST URLs (`/team`,
`/group`) are unchanged; this is purely a naming alignment.

- **CLI flags**
  - `--team-id` → `--workspace-id` (on `cupt list`, `cupt prefetch`,
    `cupt config`, `cupt teams`)
  - `cupt list --group` → `cupt list --team`
- **CLI commands**
  - `cupt groups` → `cupt teams`
- **Output / messages**
  - `cupt status` prints `Workspace:` (was `Team:`)
  - `cupt config --show` prints `Workspace ID:` (was `Team ID:`)
  - `cupt summary --all` prints `WORKSPACE SUMMARY` (was `TEAM SUMMARY`)
- **Library API**
  - `ClickUpClient.get_teams()` (returned workspaces) →
    `ClickUpClient.get_workspaces()`
  - `ClickUpClient.get_user_groups(team_id)` → `get_teams(workspace_id)`
    (returns user-groups, i.e. ClickUp UI "Teams")
  - `ClickUpClient.get_team_tasks(team_id, ...)` →
    `get_workspace_tasks(workspace_id, ...)`
  - `TaskService.list_tasks(team_id=...)` → `list_tasks(workspace_id=...)`
  - `TaskService.resolve_parent_names(team_id, ...)` →
    `resolve_parent_names(workspace_id, ...)`
  - `TaskService.get_task_context(task_id, team_id, ...)` →
    `get_task_context(task_id, workspace_id, ...)`
  - `TaskService.filter_by_groups(...)` → `filter_by_teams(...)`
  - `TimeService(client, team_id)` → `TimeService(client, workspace_id)`
  - All `team_id`-named parameters across `ClickUpClient`'s timer,
    time-entry, and space methods are now `workspace_id`.
- **Config key**
  - On disk: `user.team_id` → `user.workspace_id`. Existing
    `user.team_id` is read transparently as a fallback (see Added).
    Re-running `cupt config --workspace-id <id>` writes the new key.

## [0.6.2] — 2026-05-16

No functional or library changes. First release published automatically
via GitHub Actions Trusted Publishing (OIDC) — verifies the pipeline
introduced in commit `ceaab8a` works end to end. Future releases now
happen by tagging `v*` on `main`.

## [0.6.1] — 2026-05-16

Library-readiness pass. No CLI behavior changes; the public API surface
is now stable and importable.

### Added
- Top-level package exports: `from cupt import ClickUpClient, TaskService,
  TimeService, NoteService, APIError, AuthError, ConfigError, CuptError`.
- `TaskService.filter_by_tags(tasks, required=, excluded=)` — pure,
  reusable tag filter, promoted from a private CLI helper.
- `TaskService.list_tasks(..., tags=[...])` parameter — pushes tag
  filtering to the ClickUp API as `tags[]` (server-side OR). Replaces
  the silently-truncated client-side-only path: previously the 100-task
  pagination cap could hide matches on `--all` queries with rare tags.
- Regression tests guarding (a) the per-request `Content-Type`
  placement that prevents upload corruption and (b) the top-level
  library imports.

### Changed
- **`ConfigManager` is lazy**: constructing one no longer creates
  `~/.cupt/` or writes a default config file. Directories are
  materialized on the first write. Reads of a missing config return
  empty defaults. Library users get no surprise filesystem side
  effects from `import cupt`.
- **Error/success messages now go to stderr**, so piping
  `cupt list --json` no longer risks decorative output mixing into
  JSON consumers.
- **Emojis are TTY-only** in error/warning output; piped output gets
  plain `ERROR:` / `WARN:` prefixes.
- **`Content-Type: application/json` is now set per-request** inside
  `_make_request` instead of on the shared `requests` session. Removes
  the footgun that made attachment uploads fragile.
- **429 rate limits are retried** with exponential backoff honoring
  the `Retry-After` header (previously treated as a hard error).

### Fixed
- Silent `Exception` swallowing in cache writes now logs a warning.

## [0.6.0] — 2026-05-16

### Added
- `cupt attach list <task_id>` — show index, size, and filename for
  each attachment on a task.
- `cupt attach get <task_id> <selector> [-o path]` — download by
  1-based index or filename substring. Ambiguous matches are rejected
  rather than silently picking one.
- `cupt attach add <task_id> <file> [--name override]` — upload a
  local file as a task attachment.
- `cupt show` now prints an `Attach:` line when the task has
  attachments.
- `ClickUpClient.upload_task_attachment` — upload helper that bypasses
  the shared session to prevent multipart `Content-Type` corruption.
  This is the historically fragile part of the ClickUp API; two
  regression tests guard the implementation.

## [0.5.1] — 2026-05-16

### Added
- `cupt tag add <task_id> <name>` and `cupt tag remove <task_id> <name>`
  for managing tags on a task.

### Fixed
- `setup.py` now reads `__version__` from `cupt/__init__.py` instead
  of duplicating it. Installed-package version can no longer drift
  from source — a real bug observed during the 0.5.0 install.

## [0.5.0] — 2026-05-16

### Added
- `cupt list --tag NAME` and `--no-tag NAME` (both repeatable) —
  client-side tag filtering. `--tag` requires all named tags (AND);
  `--no-tag` excludes any task with any named tag.
- `cupt list --json` and `cupt show --json` — pipeable raw-JSON
  output for scripting. JSON mode suppresses headers, warnings, and
  background detail-caching so stdout stays clean for downstream
  consumers like `jq`.
- `cupt show` displays a `Tags:` line when tags are present.

### Note
The server-side push of `--tag` to the ClickUp API came in 0.6.1.
In 0.5.0 the filter ran purely client-side on the 100-task list view.

## [0.4.1] — 2026-04-27

### Added
- `cupt show` includes an `Assignee:` line combining individual
  usernames and team (group_assignees) names. Renders `Unassigned`
  when neither is set.

## [0.4.0] — 2026-04-27

### Changed
- List and summary output is **terminal-width aware**. The task-name
  column uses the live terminal width via `shutil.get_terminal_size()`
  (respects the `COLUMNS` env var). When stdout is piped or
  redirected, truncation is disabled entirely so downstream programs
  receive complete names.

## [0.3.0] — 2026-04-07

The big async + offline release.

### Added
- **Offline mode.** `cupt prefetch` explicitly populates per-task
  detail cache; `cupt list` transparently seeds it after display
  (≤2s budget, 8 worker threads); `cupt show --offline` reads from
  cache and falls back to the list cache with a partial-data warning.
- **`cupt summary` command** with concurrent data fetching.
- **Custom exception hierarchy:** `CuptError`, `APIError`,
  `AuthError`, `ConfigError` in `cupt/exceptions.py`.
- **Structured logging** with `--debug` / `CUPT_DEBUG` env var.
- **Verbose list columns:** Assignee (including group_assignees),
  Est, Tracked.
- Per-task JSON cache files under `~/.cupt/task_cache/`.

### Changed
- Many CLI commands now run their independent API calls in parallel
  via `ThreadPoolExecutor` (notably `cupt show`, `cupt context`,
  `cupt done`, and the new offline prefetcher).
- Version string now read from `__init__.py` rather than hardcoded
  in `main.py`.
- `clear-cache` now clears all cache layers (parent names, task list,
  per-task details).

## [0.2.0] — 2026-04-08

### Added
- Improved support for ClickUp **teams / group assignees**.
- **Phase 2 refactor:** extracted `get_client_context()` into
  `cupt/context.py`, eliminating ~6 lines of auth/client boilerplate
  per command. Moved status-finding logic from `tasks.py` into
  `TaskService`.

### Fixed
- Subtask name resolution issues when parents fell outside the
  current filter view.
- Performance improvements via in-memory config caching (load YAML
  once per `ConfigManager` instance instead of on every `get()`).

## [0.1.0] — 2026-01-03

Initial public-ready release. Covers the work from the project's
"Initial import" through "Improved test coverage and prepared for
release".

### Added
- Core CLI commands: `cupt list`, `cupt show`, `cupt done`,
  `cupt note`, `cupt context`, `cupt time start/stop`.
- ClickUp authentication via OAuth or Personal API Token.
- Subtask display (`↳`) with parent name resolution and a persistent
  parent-name cache.
- Verbose listing mode and overdue/today/week filters.
- System-wide install support via `pip install -e .` / `pipx`.
- Initial test suite with `pytest` and HTTP mocking.
