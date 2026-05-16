# Changelog

All notable changes to `cupt` are recorded here. Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] — 2026-05-16

Library-readiness pass. No CLI behavior changes; the public API surface
is now stable and importable.

### Added
- Top-level package exports: `from cupt import ClickUpClient, TaskService,
  TimeService, NoteService, APIError, AuthError, ConfigError, CuptError`.
- `TaskService.filter_by_tags(tasks, required=, excluded=)` — pure, reusable
  tag filter, previously a private helper in the CLI module.
- Regression tests guarding (a) the per-request `Content-Type` placement
  that prevents upload corruption and (b) the top-level library imports.

### Changed
- **`ConfigManager` is lazy**: constructing one no longer creates `~/.cupt/`
  or writes a default config file. Directories are materialized on the
  first write. Reads of a missing config return empty defaults.
- **Error/success messages now go to stderr**, so piping `cupt list --json`
  no longer risks decorative output mixing into JSON consumers.
- **Emojis are TTY-only** in error/warning output; piped output gets plain
  `ERROR:` / `WARN:` prefixes.
- **`Content-Type: application/json` is now set per-request** inside
  `_make_request` instead of on the shared `requests` session. This removes
  the footgun that made attachment uploads fragile.
- **429 rate limits are retried** with exponential backoff honoring the
  `Retry-After` header (previously treated as a hard error).

### Fixed
- Silent `Exception` swallowing in cache writes now logs a warning.

## [0.6.0] — 2026-05-16

### Added
- `cupt attach list/get/add` — manage task attachments.
- `ClickUpClient.upload_task_attachment` — upload helper that bypasses the
  shared session to prevent multipart `Content-Type` corruption.
- `cupt show` now reports attachment counts.

## [0.5.1] — 2026-05-16

### Added
- `cupt tag add/remove <task_id> <name>` — set or unset tags on a task.

### Fixed
- `setup.py` now reads `__version__` from `cupt/__init__.py` so installed
  package version can no longer drift from the source.

## [0.5.0] — 2026-05-16

### Added
- `cupt list --tag NAME` and `--no-tag NAME` (both repeatable). `--tag` is
  pushed to the ClickUp API as `tags[]` (server-side OR); the client-side
  AND filter narrows for stacked tags.
- `cupt list --json` and `cupt show --json` for pipeable, scriptable output.
- `cupt show` displays a `Tags:` line when tags are present.
