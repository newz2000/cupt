"""Fail when a module named in PLAN.md's v1.0 readiness criteria drops below its
coverage floor.

`pytest --cov-fail-under` gates the project total, which a large well-tested
module can hold up while a small critical one rots. Criterion 4 asks for >=80%
in `api`, `services/`, `tasks`, and `auth` specifically, so check those by name.

Run after a coverage run, which is what leaves `.coverage` behind:

    pytest --cov=cupt
    python scripts/check_coverage.py
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple

from coverage import Coverage

ROOT = Path(__file__).resolve().parents[1]

# PLAN.md, "v1.0 readiness criteria", item 4.
FLOORS: Dict[str, float] = {
    "cupt/api.py": 80.0,
    "cupt/auth.py": 80.0,
    "cupt/tasks.py": 80.0,
    "cupt/services/": 80.0,
}


def _percent(cov: Coverage, path: Path) -> float:
    _fname, statements, _excluded, missing, _fmt = cov.analysis2(str(path))
    if not statements:
        return 100.0
    return 100.0 * (len(statements) - len(missing)) / len(statements)


def _targets(rule: str) -> List[Path]:
    if rule.endswith("/"):
        return sorted((ROOT / rule).glob("*.py"))
    return [ROOT / rule]


def main() -> int:
    data_file = ROOT / ".coverage"
    if not data_file.exists():
        raise SystemExit(
            "No .coverage found — run `pytest --cov=cupt` before this check."
        )

    cov = Coverage(data_file=str(data_file))
    cov.load()

    failures: List[Tuple[str, float, float]] = []
    for rule, floor in sorted(FLOORS.items()):
        for path in _targets(rule):
            rel = path.relative_to(ROOT).as_posix()
            try:
                pct = _percent(cov, path)
            except Exception as exc:  # unmeasured file, e.g. renamed module
                raise SystemExit(f"Could not read coverage for {rel}: {exc}")
            marker = "ok " if pct >= floor else "FAIL"
            print(f"  {marker} {rel:<34} {pct:5.1f}%  (floor {floor:.0f}%)")
            if pct < floor:
                failures.append((rel, pct, floor))

    if failures:
        detail = ", ".join(
            f"{name} at {pct:.1f}% < {floor:.0f}%" for name, pct, floor in failures
        )
        raise SystemExit(f"Coverage floor not met: {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
