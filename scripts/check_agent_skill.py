"""Check that cupt commands referenced by the bundled agent skill exist."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "skill" / "cupt-clickup" / "SKILL.md").read_text()
help_text = subprocess.check_output(
    ["python", "-m", "cupt.main", "--help"], cwd=ROOT, text=True
)
commands = set()
for line in help_text.splitlines():
    match = re.match(r"  ([a-z][a-z-]*)\s", line)
    if match:
        commands.add(match.group(1))

missing = sorted(
    {m.group(1) for m in re.finditer(r"`cupt ([a-z][a-z-]*)", text)}
    - commands
    - {"--version"}
)
if missing:
    raise SystemExit("Skill references missing command(s): " + ", ".join(missing))
