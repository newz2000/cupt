# AGENTS.md

Guidelines for humans and AI assistants making changes to `cupt`.
**If you're using an LLM to contribute, this file is for it. Read all of it.**

---

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -e .
pytest                                      # 186 tests, ~0.3s
pytest tests/test_tasks.py::test_list_tasks_cli   # single test
pytest --cov=cupt --cov-report=term-missing       # with coverage
```

The pre-commit hook (see below) enforces formatting and lint. Install
once per clone: `pip install pre-commit && pre-commit install`.

---

## Project map

This is the **most important section** for an agent. Misplaced code is
the single biggest cause of low-quality PRs.

| Where               | What goes there                                        |
| ------------------- | ------------------------------------------------------ |
| `cupt/api.py`       | HTTP only. ClickUp REST endpoints. No business logic.  |
| `cupt/services/*`   | Business logic. Takes a `ClickUpClient`. No CLI/print. |
| `cupt/<topic>.py`   | CLI commands for one topic (tags, attachments, etc.). |
| `cupt/main.py`      | CLI entry point. Wires command groups. No logic.       |
| `cupt/config.py`    | Persistent config + cache. Lazy I/O (see Gotchas).     |
| `cupt/utils.py`     | Internal formatting helpers. Not part of public API.   |
| `cupt/exceptions.py`| Public exception hierarchy.                            |
| `tests/test_*.py`   | One test file per source module.                       |

**Rule of thumb:** if you find yourself adding a `requests.get(...)`
inside a service, or a `click.echo(...)` inside `api.py`, you are
putting the change in the wrong file.

---

## Public library API

After v0.6.1, `cupt` is consumed as a library too. The public surface
is whatever is exported from `cupt/__init__.py`. **Treat anything in
that file as a stability contract.**

- Renaming, removing, or changing the signature of `ClickUpClient`,
  `TaskService`, `TimeService`, `NoteService`, or the exception classes
  is a breaking change requiring a major-version bump.
- Adding new methods or classes is non-breaking.
- Anything not in `cupt/__init__.py` (CLI modules, `cupt.config`,
  `cupt.context`, `cupt.utils`) is internal and may change freely.

---

## Quality bar

These are not aspirational. PRs that miss them will be sent back.

### 1. One concern per PR
Each PR should do one thing. If you're tempted to also rename a variable,
fix an unrelated typo, or "while I'm here" refactor — that goes in a
separate PR. Drive-by changes make review impossible.

### 2. Tests required for behavior changes
- **New public function:** must have at least one test calling it.
- **Bug fix:** must include a regression test that *fails before the fix
  and passes after*. Demonstrate it by running tests on the parent commit.
- **Refactor:** test count should not decrease. Behavior tests should
  still pass without modification.

### 3. Coverage doesn't regress
Run `pytest --cov=cupt`. Total coverage should not drop. Don't game it
with `# pragma: no cover` unless the line is genuinely unreachable
(e.g. a defensive branch for a `requests` exception type we don't
believe can fire).

### 4. No speculative code
Don't add features, configuration knobs, or error handling for
scenarios that aren't real today. "Might be useful later" almost never
is. If the change isn't tied to a documented issue, real user need, or
clear improvement, explain why in the PR description.

### 5. Separation of concerns
HTTP in `api.py`. Logic in `services/`. Presentation in command
modules. If a change crosses these layers unnecessarily, restructure
before submitting.

### 6. Small commits, descriptive messages
Subject line: `<area>: <imperative summary>` (max ~72 chars).
Body: explain *why*, not *what* (the diff shows what).
If an AI assisted, include `Co-Authored-By: Claude <noreply@anthropic.com>`
(or the appropriate model).

---

## Style

- **Formatter:** `ruff format` (line length 88). The pre-commit hook
  runs this; CI rejects unformatted code.
- **Linter:** `ruff check`. Same hook.
- **Imports:** stdlib, third-party, local — separated by blank lines.
  `ruff` enforces this via the `I` rule.
- **Naming:** `snake_case` for functions/variables, `CamelCase` for
  classes, `UPPER_SNAKE` for module-level constants. Leading underscore
  for module-private helpers.
- **Type hints:** required on all public functions (anything not
  prefixed with `_`). Use `typing.Optional`, `typing.List`, etc.
- **Docstrings:** every public function. One-sentence summary is fine
  for obvious helpers; longer for anything subtle (constraints,
  side-effects, error modes).
- **Comments:** explain *why*, not *what*. If a line of code needs a
  comment because it's surprising, that's the comment to write. Don't
  paraphrase the code.

---

## Known gotchas

These are things that have bitten the project. Each one has a
regression test. **Do not "fix" them without understanding why.**

### Content-Type must NOT live on the requests Session
`ClickUpClient.session` only carries `Authorization`. JSON
`Content-Type` is set per-request inside `_make_request`. If you put
`Content-Type: application/json` back on the session,
`requests.post(..., files=...)` will be unable to generate its
multipart boundary header and **every attachment upload will silently
upload a corrupted file**. Guards:
- `tests/test_api.py::test_session_has_no_global_content_type`
- `tests/test_api.py::test_upload_task_attachment_no_json_content_type`

### `ConfigManager.__init__` does no I/O
Constructing a `ConfigManager` must not create `~/.cupt/` or read any
file. Library users may instantiate it just for the API client.
Directories are created lazily via `_ensure_dirs` on the first write.
Guard: `tests/test_config.py::test_config_lazy_initialization`.

### Pre-signed S3 URLs reject `Authorization` headers
Attachment downloads (`cupt attach get`) hit pre-signed S3 URLs from
ClickUp. Sending `Authorization` invalidates the signature. The
download path uses a plain `requests.get` with no auth header.

### Output discipline: stdout is data, stderr is decoration
Anything you print with `print_error / print_warning / print_success`
goes to **stderr**. This is what makes `cupt list --json | jq …`
reliable. Never `click.echo` an error message to stdout, and never
add a "helpful" banner to a `--json` code path.

### Server-side tag filtering
`TaskService.list_tasks(..., tags=[...])` pushes `tags[]` to the
ClickUp API (OR semantics). The client-side `filter_by_tags` then
narrows for AND semantics. Without server-side filtering, the 100-task
pagination cap silently hides matches. Don't move tag filtering
entirely client-side.

---

## Pull request checklist

Before opening a PR, confirm:

- [ ] One concern, scoped tightly. Title is one imperative sentence.
- [ ] Tests added/updated. `pytest` is green.
- [ ] `pytest --cov=cupt` shows coverage hasn't regressed.
- [ ] `pre-commit run --all-files` is clean.
- [ ] CHANGELOG.md updated under `## [Unreleased]` for any user-facing
      change.
- [ ] If AI-assisted: `Co-Authored-By:` line included in the commit
      message.

---

## When in doubt

Open a draft PR or an issue with a `## Question` section before writing
code. A 5-line "is this the right approach?" thread is much cheaper than
a 500-line PR that has to be rewritten.
