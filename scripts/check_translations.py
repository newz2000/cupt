"""Fail when gettext catalogs are missing or stale."""

import ast
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parents[1]
POT = ROOT / "cupt" / "locale" / "cupt.pot"
ES = ROOT / "cupt" / "locale" / "es" / "LC_MESSAGES" / "cupt.po"


def _msgids(path: Path) -> Set[str]:
    ids: Set[str] = set()
    current = None
    active = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("msgid "):
            if current is not None:
                ids.add(current)
            current = ast.literal_eval(line[6:].strip())
            active = "msgid"
        elif line.startswith("msgstr "):
            active = "msgstr"
        elif line.startswith('"') and active == "msgid" and current is not None:
            current += ast.literal_eval(line)
    if current is not None:
        ids.add(current)
    ids.discard("")
    return ids


missing = [str(path.relative_to(ROOT)) for path in (POT, ES) if not path.exists()]
if missing:
    raise SystemExit("Missing translation catalog(s): " + ", ".join(missing))

pot_ids = _msgids(POT)
for po in (ROOT / "cupt" / "locale").glob("*/LC_MESSAGES/cupt.po"):
    stale = sorted(pot_ids - _msgids(po))
    if stale:
        raise SystemExit(f"{po.relative_to(ROOT)} is missing msgid(s): {stale}")
