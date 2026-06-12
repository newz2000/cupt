# Performance Notes

v1.0 keeps performance work evidence-based.

## `TaskService.list_tasks`

The primary hot path is paginated task listing. The current implementation keeps
server-side filters for due dates, assignees, and tags, then applies client-side
AND tag narrowing and team filtering where the ClickUp API does not expose an
equivalent server-side filter.

Before adding new caches, profile a real workspace with:

```bash
python -m cProfile -o /tmp/cupt-list.prof -m cupt.main list --all --team <team>
python - <<'PY'
import pstats
pstats.Stats('/tmp/cupt-list.prof').strip_dirs().sort_stats('cumtime').print_stats(30)
PY
```

## v1.0 lazy-loading choice

`cupt show` no longer fetches comments unless the caller asks for notes or JSON.
That keeps the common human detail view cheaper while preserving the complete
machine-readable `show --json` shape.

## Deferred

A persisted team-to-task cache remains deferred until real workspace profiling
shows that the team page walk is a practical bottleneck.
