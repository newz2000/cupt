Overview
1. Test‑centric stability – add comprehensive unit & integration tests covering API interactions, services, and CLI commands.
2. Code cleanup & refactor – improve readability, type hints, error handling, and modularity.
3. Performance tuning – target measurable gains for critical paths (e.g., task listing, time‑entry operations).
4. Enhanced productivity features – add productivity‑driven enhancements once core stability is achieved.
Below is a detailed, step‑by‑step plan (in Markdown).
Feel free to pick or reorder sections as per your workflow.
 Cupt Project Roadmap
 Phase 1 – Stabilization (Tests & Core Fixes)
1️⃣ **Determine coverage target**
   - Aim for ≥ 80 % line/branch coverage in core modules (`api`, `services/`, `tasks`, `auth`).
2️⃣ **Implement missing test coverage**
   - [ ] **api.py**
     * Create mocks for GET/POST/PUT/DELETE → test error handling and JSON parsing.
     * Verify proper header inclusion.
   - [ ] **auth.py (OAuth flow)**
     * Mock HTTP server interactions (`OAuthCallbackHandler`).
     * Test token exchange, refresh, logout.
   - [ ] **services/task_service.py**
     * Verify task‑listing filters, pagination, closed‑status resolution.
     * Mock ClickUpClient for task fetching.
   - [ ] **services/timer_service.py**
     * Test `start_timer`, `stop_timer`, `add_time_entry` logic.
   - [ ] **cli commands**
     * Use `click.testing.CliRunner` to assert command outputs and error handling.
3️⃣ **Regression test matrix**
   - Run existing `tests/` and new tests with `pytest --cov` and ensure failures are reproducible.
4️⃣ **Add test harness**
   - Create a `tests/conftest.py` for shared fixtures (mocked ClickUpClient, test config loader).
5️⃣ **CI configuration**
   - Draft a CI pipeline (GitHub Actions) that runs tests, lints (flake8/black), and builds the package.
6️⃣ **Document testing strategy**
   - Update `README.md` with a "Testing" section (how to run tests, interpret coverage).
 Phase 2 – Code Refactor & Cleanup
7️⃣ **Improve type hints and imports**
   - Add `typing` annotations for all public functions.
   - Remove unused imports.
8️⃣ **Centralize configuration**
   - `ConfigManager` exposes `get`, `set`, and `load_cache`. Refactor to use a schema‑driven approach (pydantic or dataclasses).
9️⃣ **Error handling**
   - Introduce custom exceptions (`APIError`, `AuthError`).
   - Replace generic `Exception` in `api._make_request`.
🔟 **Logging**
   - Add a logger (`logging.getLogger(__name__)`) instead of `print_*` utilities.
1️⃣1️⃣ **Code formatting**
   - Apply `black` and `isort` uniformly.
1️⃣2️⃣ **Modularize CLI commands**
   - Split `tasks.py` into separate modules (`list_cmd.py`, `show_cmd.py`, `done_cmd.py`).
1️⃣3️⃣ **Refactor service classes**
   - Make `TaskService`, `TimerService`, `NoteService` each a small, focused class.
 Phase 3 – Performance Enhancements
12️⃣ **Profile critical paths**
   - Use `cProfile` or `timeit` on `TaskService.list_tasks`.
   - Identify bottlenecks: repeated API calls, JSON deserialization, cache misses.
13️⃣ **Batch API usage**
   - For bulk task fetching, leverage `get_tasks_by_ids` with pagination.
14️⃣ ~~**Client‑side caching**~~  ✅
   - ~~Cache parent task names and status lists to avoid repeated lookups.~~
15️⃣ **Lazy loading**
   - Defer fetching of optional fields (e.g., subtasks) until needed.
15️⃣ᵃ **Team → task mapping cache** *(post-0.7.1, only if telemetry warrants)*
   - The 0.7.1 fix walks more pages for `--team` queries instead of stopping at 100 results, which works but adds 5–15s of latency on `--all --team` against a large workspace.
   - Pre-walk the workspace once per session (or with a TTL), persist `{team_id: [task_id, …]}` in `~/.cupt/teams_cache.json`, then satisfy subsequent `--team` queries by looking up cached IDs and fetching only those tasks.
   - Stale-cache risk: new tasks assigned to a team since the last walk will be missed. Need a `cupt teams --refresh` to invalidate.
   - Don't build until real usage shows the page-walk latency is actually painful. The fast path (`--team` + `--tag`) may make this unnecessary.
 Phase 4 – Productivity Features
16️⃣ **Auto-complete task notes**
   - Provide a `--auto-note` flag that suggests a note based on task title/description.
   - *AI enhancement candidate — see Phase 5.*
17️⃣ **Daily summary**
   - CLI command `cupt summary` that aggregates tasks due today, time logged, and closed tasks.
   - Defaults to `--mine` (same as `cupt list`); accepts `--all` to show team-wide.
   - API calls run concurrently: today's tasks, overdue tasks, running timer, time entries for the day, tasks closed today.
   - *AI enhancement candidate — see Phase 5.*
18️⃣ **Time-tracking shortcuts**
   - Add `start <task-id>`, `stop`, `add <hours>`, and `report`.
19️⃣ **Offline support** *(investigate)*
   - Explore caching the full task list locally so read-only commands (`list`, `show`, `context`) work without a network connection.
   - Consider a TTL-based cache refresh strategy and a `--offline` flag to force local data.
19️⃣ᵃ **Team filter for `cupt list`** ✅ *(shipped 2026-05-30; renamed to match ClickUp UI in same window)*
   - ClickUp distinguishes the **workspace** (`--workspace-id`, previously `--team-id`) from **teams** (user-groups within the workspace, e.g. "MattTech", "AI Agent"). Teams show up on tasks as `group_assignees` in the JSON.
   - `cupt list --team <name|id>` (repeatable, OR semantics) stacks cleanly with `--tag`, `--no-tag`, `--mine`/`--all`, and the date filters.
   - `cupt teams` lists `id`, `name`, and member count for the workspace.
   - Filter runs client-side by walking `task.group_assignees[].id` (ClickUp's filter API doesn't expose team assignees server-side, so result quality depends on pagination — combine with `--all` if a team's tasks are rare).
20️⃣ᵃ **Per-list status discovery and "mark complete" normalization** ✅ *(shipped 2026-05-30)*
   - `cupt statuses <task-id>` (or `--list <list-id>`) — print all statuses available for a list, with the one `cupt done` would apply marked. Supports `--json`.
   - `cupt done --dry-run` — resolve and print the target status without mutating.
   - `TaskService.resolve_completion_status(task_id)` — pure helper documented in AGENTS.md as the canonical entry point.
   - Multi-list regression: `tests/test_task_service.py::test_complete_task_resolves_per_list_not_globally` proves two tasks in lists with different closed names each get the right one.

24️⃣ **`cupt work` / `cupt gtd` — sequential focused-work mode**
   - Take a filter (`--tag ai_ready`, etc.), present one task at a time with full context, and walk through them with `[w]ork / [s]kip / [d]one / [q]uit` prompts.
   - GTD-flavored variant: enforce a single "currently doing" task at a time; integrate with `cupt time start/stop` so timing is automatic.
   - Open question: does this stay shell-interactive, or get a `--script <path>` mode that lets an agent drive it programmatically?

25️⃣ **Quick Create** ✅ *(shipped 2026-06-09 in v0.8.0)*
   - `cupt add "Title"` — captures into the active task's list (or `user.default_list_id`) with you as assignee.
   - `--parent <id|short|this>` / `--blocks <id|short|this>` for relationships; `this` resolves to the active task.
   - `--description`, `--due` (today/tomorrow/+Nd/YYYY-MM-DD/epoch ms), `--tag` (repeatable), `--json`.
   - `ClickUpClient.create_task` and `ClickUpClient.add_task_dependency` exposed as library methods.
   - Agent skill (`skill/cupt-clickup/SKILL.md`) updated to drop the "use MCP for creation" redirect.

26️⃣ **Workflow state / persistent session** ✅ *(shipped 2026-06-09 in v0.8.0)*
   - `~/.cupt/state.json` tracking the active task and Taskwarrior-style short IDs.
   - `cupt start <id>` sets active; subsequent `note`/`done`/`show`/`context`/`notes`/`time start`/`time add` default to it; `cupt done` clears it; `cupt stop` clears without closing; `cupt active` reads.
   - Short IDs (`#` column in `cupt list`) reconcile on unfiltered `--mine` lists and are additive on filtered views. Freed on done.
   - Both features auto-hide when stdout is a pipe / `CI=true` / `--no-interactive` / `CUPT_INTERACTIVE=0` — agents and scripts keep their stateless contract.
   - Open follow-ups: `cupt next` queue advancement (still future); `cupt work` (item 24️⃣) can now layer on top of this state.

27️⃣ **Shell completion**
   - `click` supports zsh/bash/fish completion natively via `_CUPT_COMPLETE`. Document the install snippet per shell.
   - Stretch: dynamic completion of task IDs, list IDs, team names from `~/.cupt/` cache (only completes on commands that take them).

28️⃣ **Saved Views support** *(server-side filter escape hatch)*
   - `cupt list --view <view-id>` would hit `/view/{view_id}/task` and let users lean on ClickUp's UI to configure any filter the API supports (including by team-as-group, which we can't filter server-side ourselves).
   - Helpful for the pathological case the team-filter fix can't reach: rare team tasks deep in a huge workspace.
   - `cupt views` discovery command to list available view IDs alongside their names.
 Phase 5 – Local AI Integration *(future, needs design review first)*
   OS-level AI tools are becoming standard on both macOS and Windows. cupt is well-positioned to use them, but **before expanding this work we need to think harder about whether it's actually useful for our audience.** The current Apple-Intelligence-only `--auto-note` flag is partial Phase 5 and went largely unused; that should inform the next pass.

   **Open design questions to resolve before writing more code:**
   - Who is this for? `cupt` users skew toward power-users / engineers / agent-driven workflows. Do they actually want AI-drafted notes, or do they want raw data they can pipe into their own tooling (which already works via `--json`)?
   - What does "good" look like? A completion-note suggestion has to clear a quality bar — a generic "Completed the task as described" is worse than no suggestion. How do we measure that?
   - Where is the friction worst? `cupt summary --ai` might be more valuable than `cupt done --auto-note` because the summary involves more synthesis. Worth prototyping before committing to an abstraction.
   - Backend story: is local-only the right constraint? Cloud AI (Claude, OpenAI) gives much better output but adds privacy/cost considerations that change who the audience is.
   - Should it stay in core, or live in a separate `cupt-ai` plugin so the base CLI stays lean?

20️⃣ **AI backend abstraction** *(blocked on design review above)*
   - Introduce an optional `AIProvider` interface in `cupt/ai.py` with a single `complete(prompt) -> str` method.
   - Candidate backends (priority TBD):
     1. **Ollama** — query `http://localhost:11434` (cross-platform, developer-friendly)
     2. **Apple Intelligence / MLX** — already partially shipped via `apple-fm-sdk`; needs to be folded into the abstraction
     3. **Windows Copilot** — invoke via WinRT `Microsoft.Windows.AI` APIs (Windows 11)
     4. **Claude API** — fallback if an `ANTHROPIC_API_KEY` env var is set
   - If no backend is available, features that require AI are silently skipped or show a friendly hint.

21️⃣ **AI-enhanced `--auto-note`** *(partial: Apple Intelligence works today; blocked on design review for broader rollout)*
   - Already implemented for `apple-fm-sdk`. Pulls task title, description, and recent comments; presents suggestion with `[a]ccept / [e]dit / [s]kip`.
   - Not declared as a dependency or surfaced in the README — see design-review notes above before changing that.

22️⃣ **AI-enhanced `cupt summary`** *(not started)*
   - After assembling the raw summary data, optionally pass it to the AI backend for a one-paragraph plain-English callout.
   - Example output: "You have 2 overdue items — the client inquiry from Monday looks most urgent. You've tracked 3h 45m today, slightly under your usual pace."
   - Controlled by a `--ai` flag so it's opt-in; raw summary always shown first.
 Phase 6 – Pie in the Sky *(future, after Phase 5)*
23️⃣ **Policy ingestion from ClickUp documents**
   - Idea: when processing a task, look up the list or folder it lives in and check whether a designated document (e.g., one tagged `policy` or named `AGENT_POLICY.md`) lives there. If found, pull its contents and feed them to the agent as system-level guidance before it acts on the task.
   - Open questions to resolve before implementing:
     * Discovery rule — naming convention vs. tag vs. explicit pointer in folder metadata?
     * Scope — does a folder-level policy override a list-level one? How are conflicts resolved?
     * Caching — policies will change rarely; cache aggressively with a manual `cupt policy refresh`.
     * Surface — is this an implicit feature (agents always see policies) or opt-in via `cupt policy show <task-id>` and a `--with-policy` flag?
   - Likely depends on the AIProvider abstraction from Phase 5, so park here until that lands.

 Phase 7 – Internationalization *(v1.0 release target)*
   The CLI's user-facing surface is small and stable enough that AI-assisted translation should produce shippable results with native-speaker review. Doing this before 1.0 means the API contract (translatable strings, message catalog format) is settled before the version commitment.

29️⃣ **i18n infrastructure**
   - Adopt Python's stdlib `gettext` with `babel`/`pybabel` for the tooling.
   - Audit every `click.echo`, `print_*` call, every `--help` string, every error/warning message; wrap user-visible literals in `_()` markers.
   - Generate the source `.pot` catalog. Add a `pybabel extract` invocation to the dev workflow.
   - Add `--lang <code>` flag and a `CUPT_LANG` env var (falls back to the system locale).
   - Library API (`ClickUpClient`, `TaskService`, etc.) returns raw data with English-language exception messages — translation is a CLI-only concern.

30️⃣ **AI-assisted translation pipeline**
   - Use a strong cloud model (Claude or GPT-class) to bootstrap translations for an initial language set — Spanish, French, German, Japanese, Brazilian Portuguese, Simplified Chinese as a starting point. The CLI strings are short and context-light, which is the sweet spot for high-quality machine translation.
   - **Quality bar before shipping a language:** native-speaker review of the full catalog. Don't ship a half-correct translation that frustrates the audience it was meant to help.
   - Recruit reviewers via the GitHub repo (open an issue inviting native speakers per language) before shipping `cupt` 1.0.
   - Maintenance: every new user-facing string should trigger a translation update for shipped languages. Add a CI check that fails if `.po` files are stale relative to `.pot`.
   - Out of scope for 1.0: RTL-language layout tweaks (the table-style output is left-to-right anyway), translated documentation (README/PLAN/AGENTS stay English-only). Revisit post-1.0 if there's demand.

31️⃣ **v1.0 readiness checklist** *(deferred until 29 + 30 land plus Phase 5 design questions are resolved)*
   - Public API stability statement (anything in `cupt/__init__.py` is now a SemVer contract).
   - Deprecation policy documented (how long do renamed CLI flags keep an alias?).
   - i18n shipping with at least 3 reviewed languages plus English.
   - Phase 5 (AI) decision resolved either way — either shipped behind a clear flag, or formally removed from the roadmap so 1.0's surface is honest.

 Deliverables
- Updated test suite with ≥ 80 % coverage.
- Clean, type‑annotated, well‑logged code.
- Performance‑instrumented CLI with optional `--profile` flag.
- README updates (overview, installation, testing, usage).
---
 Next Steps to Begin
1. **Create test skeletons** (e.g., `tests/test_api_client.py`).
2. **Set up a local virtualenv** with `pip install -e .` (deps declared in `pyproject.toml`).
3. **Run `pytest --cov`** to get baseline coverage.
4. **Iteratively add mocks and assertions** as outlined.
