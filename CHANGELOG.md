# Changelog

All notable changes to `cupt` are recorded here. Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entry style: each release lists user-visible changes grouped under
**Added** (new features), **Changed** (behavior changes), **Fixed**
(bug fixes), and **Removed** (deletions). Internal refactors with no
user impact are not listed.

## [Unreleased]

(nothing yet)

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
- **Local-AI completion notes.** `cupt done --auto-note` calls a
  local AI provider (Apple Intelligence on macOS 26+) for a
  suggested completion note. Gracefully no-ops on machines without
  the SDK.
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
