# Cupt Roadmap to v1.0

## Target audience

Everything on this roadmap should serve one of two users. Features that
don't aren't on the path to 1.0.

1. **Solo finisher** — wants to work down their todo list and close
   tasks fast, with minimal context-switching. Lives in the terminal.
   The win is fewer keystrokes between "what's next" and "done."
2. **AI agent (and the team using it)** — drives cupt to coordinate with
   the humans on the team. The win is a stable, scriptable contract:
   predictable JSON, predictable exit codes, no interactive prompts when
   stdout isn't a TTY.

## v1.0 readiness criteria

1. **Stable public API.** Anything in `cupt/__init__.py` and every
   documented CLI flag is a SemVer contract. Deprecation policy
   documented.
2. **Stable agent contract.** Every read command's `--json` output is
   schema-documented; exit codes are documented; non-interactive mode
   is exercised in CI.
3. **Solo focus mode shipped** (`cupt work` / `cupt gtd`, item below).
4. **Test coverage ≥ 80 %** in `api`, `services/`, `tasks`, `auth`.
5. **i18n infrastructure in place** with at least one non-English
   language available (rough pass; quality polish can continue
   post-1.0). See section E.
6. **`--auto-note` removed** unless user research surfaces real demand
   between now and the next release. See section F.
7. **README + AGENTS.md** reflect the shipped surface.

Anything labeled *(deferred)* below is explicitly out of scope for 1.0.
We can ship it post-1.0 without breaking the SemVer promise as long as
we don't add it to the public API surface first.

---

## Already shipped (reference, not work)

These are the load-bearing capabilities the rest of the plan assumes
exist. Listed so we don't accidentally re-plan them.

- **Quick capture** — `cupt add "Title"` with `--parent this` /
  `--blocks this`, due-date parsing, tag support, `--json`. (v0.8.0)
- **Workflow state** — `~/.cupt/state.json`, active task pointer
  (`cupt start` / `stop` / `active`), Taskwarrior-style `#` short IDs
  in `cupt list`. Auto-hides for pipes / `CI=true` / `--no-interactive`.
  (v0.8.0)
- **Team filter** — `cupt list --team <name|id>` stacks with
  `--tag` / `--mine` / `--all` / date filters. `cupt teams` discovery.
  (v0.7.0)
- **Per-list status resolution** — `cupt done` picks the right closed
  status per task's list; `cupt statuses <id>` shows options;
  `cupt done --dry-run` previews. (v0.7.0)
- **Client-side caching** — parent task names and status lists.
- **Offline read path** — `cupt list` caches what it showed;
  `cupt show <id> --offline` and `cupt prefetch`.

---

## v1.0 work

### A. Stability — tests, lint, CI

Non-negotiable for the SemVer promise. Most of this is mechanical.

- [x] **Coverage to ≥ 80 %** in `api`, `services/`, `tasks`, `auth`.
  Existing test layout is fine; fill the gaps.
  * `api.py` — mock GET/POST/PUT/DELETE, error paths, header inclusion.
  * `auth.py` — mock `OAuthCallbackHandler`, token exchange, refresh,
    logout.
  * `services/task_service.py` — filters, pagination, closed-status
    resolution (multi-list regression already exists).
  * `services/timer_service.py` — start, stop, add manual entry.
  * `cli` — `click.testing.CliRunner` for every command's happy path
    and one error case.
- [x] **Shared fixtures** in `tests/conftest.py` (mocked
  `ClickUpClient`, test config loader).
- [x] **CI pipeline** (GitHub Actions): `pytest --cov`, `ruff check` /
  `ruff format --check`, build wheel + sdist. Fail the build below coverage
  target.
- [x] **Custom exceptions** (`APIError`, `AuthError`) replacing generic
  `Exception` in `api._make_request`. Stable exit-code mapping in CLI
  layer — agents consume these.
- [x] **Logging via `logging.getLogger(__name__)`** replacing ad-hoc
  `print_*` utilities. `--verbose` / `--quiet` already exist; route
  through the logger.
- [x] **Ruff format + import sorting** uniform pass; add to CI.
- [x] **Type hints on public functions** in `cupt/__init__.py` exports
  and service classes. Not asking for strict mypy — just enough that
  the SemVer surface is legible.

### B. Solo finisher — close the loop

The minimum that makes "work down my list" feel obviously better than
the alternative.

- [x] **`cupt work` — sequential focus mode.** Take a filter
  (`--tag ai_ready`, etc.), present one task at a time with full
  context, walk through with `[w]ork / [s]kip / [d]one / [q]uit`.
  Integrates with `cupt time start/stop` so timing is automatic. Sits
  on top of the v0.8.0 active-task state — `[w]ork` is just `cupt start`
  under the hood.
  * GTD-flavored: enforce a single active task at a time.
  * Open question still: shell-interactive only, or also `--script
    <path>` to let an agent drive it? Default: shell-only for 1.0; the
    agent already has `cupt start` + `cupt done` to script the same
    flow.
- [x] **Shell completion.** `click` supports zsh/bash/fish via
  `_CUPT_COMPLETE`. Document the install snippet per shell in README.
  * Stretch (only if cheap): dynamic completion of task IDs / team
    names from `~/.cupt/` cache.
- [x] **`cupt summary` — daily summary.** Aggregate today's tasks,
  overdue, running timer, time entries for the day, tasks closed today.
  Defaults to `--mine`; `--all` for team-wide. API calls run
  concurrently. `--json` is mandatory (agents consume this too).

### C. Agent contract — make the scripting contract explicit

The agent skill already exists; this is about making the surface it
relies on durable.

- [x] **JSON schemas documented** for every read command's `--json`
  output. Living doc in `AGENTS.md` or a `docs/json-schemas.md`.
  Schemas are tested — a snapshot test catches accidental breakage.
- [x] **Exit code table documented.** 0 success, 1 generic failure, 2
  auth failure, 3 not found, etc. — pick the mapping, write it down,
  test it.
- [x] **`--no-interactive` exercised in CI.** Run the full CLI surface
  with `CUPT_INTERACTIVE=0` and assert no command prompts, no short-ID
  resolution, no active-task fallback.
- [x] **Agent skill maintenance.** When commands change, update
  `skill/cupt-clickup/SKILL.md` in the same PR. Add a CI check that
  fails if the skill file references commands that don't exist.

### D. Internationalization — rough pass

The CLI surface is small and stable enough that an AI-bootstrapped pass
should land us a shippable v1.0 baseline. Doing this *before* 1.0 means
the catalog format and the wrapping convention are part of the SemVer
contract — adding strings post-1.0 stays cheap; switching frameworks
later wouldn't be.

- [x] **gettext + babel/pybabel** wired into the dev workflow. Add
  `pybabel extract` to the release checklist.
- [x] **Audit and wrap** every `click.echo`, `print_*`, `--help`
  string, error message in `_()` markers. The library API
  (`ClickUpClient`, `TaskService`, raised exceptions) stays English —
  translation is a CLI-only concern.
- [x] **`--lang <code>` flag and `CUPT_LANG` env var**, falling back to
  the system locale. Document in README.
- [x] **Generate `.pot` source catalog**, commit it to the repo.
- [x] **AI-bootstrap one language end-to-end** as the proof point.
  Spanish is the obvious pick (largest non-English audience overlap with
  the terminal/developer crowd). Quality bar: the strings shouldn't
  embarrass us, but native-speaker review can land after 1.0 — open a
  GitHub issue inviting reviewers when we tag.
- [x] **CI check**: fail the build if `.po` files are stale relative to
  `.pot`. Stops new English strings from silently breaking
  translations.

Out of scope for 1.0: RTL layout tweaks (table output is LTR anyway),
translated README/AGENTS/CHANGELOG, more than one shipped language
beyond English. All of those can come after 1.0 without breaking the
infrastructure contract.

### E. `--auto-note` — removed for v1.0

**Status: removed for v1.0.** The implementation was small,
mostly self-contained (`cupt/ai.py` + `_get_auto_note` in
`cupt/tasks.py`), and was always documented as partial. Removing it
makes 1.0's surface honest — we're not promising "AI features" we
don't believe in.

**How it works today, plainly:**

1. Reads the task name, description (first 400 chars), and the last 3
   comments.
2. Asks Apple Intelligence (`apple-fm-sdk`, on-device, macOS 26+) to
   write *"a brief, professional one-sentence completion note."*
3. Presents the suggestion with `[a]ccept / [e]dit / [s]kip`.

The suggestion has no signal of *what the user actually did* — it's a
restatement of the task description in past tense. That's why it feels
like magic: it is, in the bad sense. "Call the client back" becomes
"Called the client back as requested" regardless of whether the call
happened or what was said.

**Removal decision:**

- No in-repo usage signal was found.
- v1.0 removes the flag, drops the optional AI helper, deletes `cupt/ai.py`
  and `_get_auto_note`.

**Reframe for later (not 1.0):** evidence-based completion notes.
Instead of paraphrasing the task description, surface signals from work
that actually happened — git commits referencing the task ID, time
entries logged today, recent file changes in a linked repo. That's a
fresh feature with a real input, not a tweak to this one. Park it.

### F. Performance — only what shows up in real use

- [x] **Profile `TaskService.list_tasks`** once with `cProfile` against
  a realistic workspace. Verified locally on 2026-06-11; see
  `docs/performance.md`. Don't pre-optimize.
- [x] **Lazy loading** for optional fields (subtasks) on `show` /
  `context` paths.
- [x] **Team → task mapping cache** *(deferred; needs a dedicated design)* —
  local v1.0 verification found that `--all --team` can take about
  31-37s when the 10-page cap is hit, while pairing `--team` with a
  selective `--tag` stayed near 2-3s. A cache could pre-walk once per
  session with TTL and persist
  `{team_id: [task_id, …]}` in `~/.cupt/teams_cache.json`,
  `cupt teams --refresh` to invalidate. Do not build it in the
  verification patch; treat it as post-v1.0 performance work.

---

## Deferred past v1.0

Removed from the critical path. Listed so we don't forget the thinking,
not as commitments.

### Saved Views support
`cupt list --view <view-id>` hitting `/view/{view_id}/task` — server-
side filter escape hatch for cases the team-filter walk can't reach.
Useful, but not load-bearing for either audience. Park.

### Local AI integration (was Phase 5)

Cut from the v1.0 critical path. The thinking:

- The agent audience **is** the AI. cupt being a thin, fast, scriptable
  pipe (`--json`) is the right primitive for them — they don't want
  cupt to also pick an LLM backend.
- The one local-AI feature we shipped (`--auto-note`) was removed on the
  v1.0 path.
- A `cupt summary --ai` callout might be the one place AI synthesis
  beats raw data, but that's a post-1.0 experiment, not a 1.0 promise.

If a `cupt-ai` plugin makes sense post-1.0, it lives outside core.

### Policy ingestion from ClickUp documents (was Phase 6)
Interesting for the agent audience — list/folder-scoped policies that
agents see before acting. But it depends on a stable agent contract
(item C above) being in place first, and the design questions
(discovery rule, scope/override, caching, opt-in vs implicit) are
unresolved. Park until post-1.0.

### Misc deferred
- Configuration via pydantic/dataclasses schema — current
  `ConfigManager` works fine; refactor only if the type-hint pass
  surfaces real pain.
- Splitting `tasks.py` into per-command modules — cosmetic; defer.
- `--profile` flag exposing `cProfile` output — useful for us, not for
  users; keep as a dev-only ad-hoc.
