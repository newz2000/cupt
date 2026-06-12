"""Fail when gettext catalogs are missing or stale."""

import ast
import sys
from pathlib import Path
from typing import Optional, Set

ROOT = Path(__file__).resolve().parents[1]
POT = ROOT / "cupt" / "locale" / "cupt.pot"
LOCALE_ROOT = ROOT / "cupt" / "locale"
CALL_NAMES = {
    "_",
    "format_message",
    "print_error",
    "print_info",
    "print_success",
    "print_warning",
}


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


def _literal(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _source_msgids() -> Set[str]:
    ids: Set[str] = set()
    for path in (ROOT / "cupt").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr

                if name in CALL_NAMES and node.args:
                    value = _literal(node.args[0])
                    if value:
                        ids.add(value)

                if name == "option":
                    for kw in node.keywords:
                        if kw.arg in {"help", "prompt"}:
                            value = _literal(kw.value)
                            if value:
                                ids.add(value)

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not any(
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in {"command", "group"}
                    for dec in node.decorator_list
                ):
                    continue
                doc = ast.get_docstring(node)
                if doc:
                    ids.add(doc)
    return ids


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in (POT,) if not path.exists()]
    po_files = sorted(LOCALE_ROOT.glob("*/LC_MESSAGES/cupt.po"))
    if not po_files:
        missing.append("cupt/locale/*/LC_MESSAGES/cupt.po")
    if missing:
        raise SystemExit("Missing translation catalog(s): " + ", ".join(missing))

    source_ids = _source_msgids()
    pot_ids = _msgids(POT)
    missing_from_pot = sorted(source_ids - pot_ids)
    if missing_from_pot:
        raise SystemExit(
            f"{POT.relative_to(ROOT)} is missing msgid(s): {missing_from_pot}"
        )

    stale_pot = sorted(pot_ids - source_ids)
    if stale_pot:
        raise SystemExit(f"{POT.relative_to(ROOT)} has stale msgid(s): {stale_pot}")

    for po in po_files:
        missing_from_po = sorted(pot_ids - _msgids(po))
        if missing_from_po:
            raise SystemExit(
                f"{po.relative_to(ROOT)} is missing msgid(s): {missing_from_po}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
