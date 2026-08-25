# cupt Agent Workflow Examples

These are multi-step workflows for AI agents. Assumes cupt is installed
and authenticated (`cupt status` confirms). For command reference see SKILL.md.

---

## 1. Process a tagged work queue

The most common agent pattern: pull tasks with a specific tag, work each
one, mark complete with a note.

```bash
# 1. Preview the queue
cupt list --tag ai_ready --json > /tmp/queue.json

# 2. Inspect the queue before acting
cat /tmp/queue.json | jq '.[] | {id: .id, name: .name, list: .list.name}'

# 3. For each task: dry-run completion first
cupt done <id> --dry-run      # confirms the status name for that task's list

# 4. Complete with a note
cupt done <id> --note "Completed by AI agent: <brief summary of what was done>"
```

Never extract the status name from step 3 and reuse it for other tasks.
Each task may live in a different list with a different closed-status name.
Call `cupt done` per task individually.

---

## 2. Scope work to a specific team

When an agent processes work delegated to a team (e.g. "AI Agent" in
ClickUp), filter to only that team's tasks to avoid acting on work owned
by humans.

```bash
# Confirm the team name first (one-time setup check)
cupt teams

# List AI Agent tasks tagged ai_ready
# Use --all because tasks assigned to a team (not a specific person)
# do not match the default --mine filter.
cupt list --all --tag ai_ready --team "AI Agent" --json

# Stack with date filter for urgent items
cupt list --all --tag ai_ready --team "AI Agent" --overdue --json
```

Why `--all` and not the default `--mine`: in ClickUp, a task can be
assigned to a team-as-group OR to specific users. `--mine` matches only
tasks where the current user is in the individual assignees list. Team
assignments live in a separate field, so `--mine --team` silently misses
group-only assignments. `--all --team` catches both.

---

## 3. Inspect before acting

Before modifying a task, pull full context. Avoid acting on stale or
incomplete information.

```bash
# Full task detail
cupt show <id> --json

# Check existing comments before adding a duplicate note
cupt notes <id> --json

# Check parent and sibling tasks before completing
# (completing a subtask when the parent is blocked is usually wrong)
cupt context <id> --json
```

---

## 4. Safe multi-task completion loop

When completing multiple tasks from a filtered list, resolve each one
independently. This shell pattern is safe across mixed-list results:

```bash
# Extract IDs from a tagged queue
TASK_IDS=$(cupt list --tag ai_ready --json | jq -r '.[].id')

# Dry-run the whole batch first to spot unexpected status names
for id in $TASK_IDS; do
  echo "--- $id ---"
  cupt done $id --dry-run
done
```

**STOP and read the dry-run output before continuing.** If any dry-run
shows an unexpected resolved status (e.g. `"In Progress"` rather than a
closed-type status like `"Done"` or `"Complete"`), that task's list
lacks a proper closed-status configuration. Investigate before
completing — marking it would change its state but not mark it closed.

Only after the dry-run output looks correct:

```bash
for id in $TASK_IDS; do
  cupt done $id --note "Processed in batch run $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done
```

---

## 5. Add context before handing off to a human

When an agent completes its portion of a task but a human needs to
finish it, leave a structured note and re-tag rather than completing.

```bash
# Leave a handoff note
cupt note <id> "AI completed: <what was done>. Needs human review: <what's needed>"

# Remove the ai_ready tag, add a review tag
cupt tag remove <id> ai_ready
cupt tag add <id> needs_review
```

This keeps the task in a visible state for the human without marking it
done prematurely.

---

## 6. Handle an empty queue

A common agent failure mode: zero tasks returned, agent panics or
invents work. An empty result is a valid outcome.

```bash
cupt list --tag ai_ready --json
# Returns []
```

Before escalating to the user, check the obvious causes:

```bash
# Tag spelling: list all tags currently in use
cupt list --all --json | jq -r '.[] | .tags[]?.name' | sort -u

# Try --all in case the work is assigned to a team rather than to you
cupt list --all --tag ai_ready --json

# Verify the team name spelling
cupt teams
```

If all three pass and the queue is still empty, the agent has no work to
do. Idle. Report the empty queue to the user. Do not fabricate tasks or
act on stale instructions.
