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

## Local v1.0 verification

Measured on 2026-06-11 against a real authenticated ClickUp workspace using the
v1.0 checkout at `976b26c`. Workspace, team, tag, task names, task IDs, and user
details are intentionally redacted.

Because this machine also had an older `cupt` on PATH, commands were run with
`PATH=venv/bin:$PATH` so the editable v1.0 checkout was measured. Task output
went to `/tmp`; only aggregate counts, page-walk footers, and timing summaries
were retained.

| Scenario | Returned | Pages | Cap hit | Wall time (`real`, 3 runs) |
| --- | ---: | ---: | :---: | --- |
| `cupt list --mine --json` | 100 | n/a | n/a | 3.23s, 2.02s, 2.58s |
| `cupt list --all --json` | 100 | n/a | n/a | 4.10s, 2.09s, 3.09s |
| `cupt list --all --team [TEAM]` | 41 | 10 | yes | 37.30s, 35.46s, 30.80s |
| `cupt list --all --team [TEAM] --tag [TAG]` | 11 | <=1 | no | 2.51s, 3.23s, 3.09s |
| `cupt work --all --team [TEAM] --json` | 41 | 10 | yes | 28.94s, 22.42s, 21.65s |
| `cupt summary --json` | 7 summary items | n/a | n/a | 0.81s, 1.04s, 0.89s |

`cProfile` on `cupt list --all --team [TEAM]` reported 28.033s total runtime.
The hot path was network-bound:

- `TaskService.list_tasks`: 25.759s cumulative.
- `ClickUpClient.get_workspace_tasks`: 10 calls, 25.757s cumulative.
- `requests`/SSL socket reads dominated the remaining cumulative time.

The team-filter cost is therefore the expected ClickUp pagination cost: the CLI
must fetch candidate task pages before applying the client-side team filter.
Selective tags materially reduce that cost because `tags[]` narrows the
candidate set server-side before team filtering runs.

## v1.0 lazy-loading choice

`cupt show` no longer fetches comments unless the caller asks for notes or JSON.
That keeps the common human detail view cheaper while preserving the complete
machine-readable `show --json` shape.

## Deferred

A persisted team-to-task cache remains deferred to a dedicated performance
design. The verification above shows the page walk can be painful for
workspace-wide team queues, but this patch records the evidence and corrects the
documentation rather than adding a speculative cache contract.
