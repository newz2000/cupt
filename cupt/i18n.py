"""CLI translation helpers."""

import ast
import gettext
import locale
import os
from pathlib import Path
from typing import Any, Dict, Optional

_TRANSLATION = gettext.NullTranslations()


class _PoTranslations(gettext.NullTranslations):
    """Tiny gettext-compatible reader for committed text-only ``.po`` files."""

    def __init__(self, path: Path):
        super().__init__()
        self._catalog = _read_po_catalog(path)

    def gettext(self, message: str) -> str:
        """Return a translated string, or the original message when missing."""
        return self._catalog.get(message, message)


def _read_po_catalog(path: Path) -> Dict[str, str]:
    """Read simple msgid/msgstr entries from a gettext PO catalog."""
    catalog: Dict[str, str] = {}
    msgid: Optional[str] = None
    msgstr: Optional[str] = None
    current: Optional[str] = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            if msgid and msgstr:
                catalog[msgid] = msgstr
            msgid = ast.literal_eval(line[6:].strip())
            msgstr = ""
            current = "msgid"
        elif line.startswith("msgstr "):
            msgstr = ast.literal_eval(line[7:].strip())
            current = "msgstr"
        elif line.startswith('"') and current == "msgid" and msgid is not None:
            msgid += ast.literal_eval(line)
        elif line.startswith('"') and current == "msgstr" and msgstr is not None:
            msgstr += ast.literal_eval(line)

    if msgid and msgstr:
        catalog[msgid] = msgstr
    return catalog


def configure_language(lang: Optional[str] = None) -> str:
    """Configure gettext for CLI strings and return the selected language code."""
    selected = lang or os.environ.get("CUPT_LANG")
    if not selected:
        selected = (locale.getlocale()[0] or "en").split("_")[0]

    po_path = (
        Path(__file__).resolve().parent
        / "locale"
        / selected
        / "LC_MESSAGES"
        / "cupt.po"
    )
    global _TRANSLATION
    if po_path.exists():
        _TRANSLATION = _PoTranslations(po_path)
    else:
        _TRANSLATION = gettext.NullTranslations()
    return selected


def _(message: str) -> str:
    """Translate a CLI message."""
    translated = _TRANSLATION.gettext(message)
    if translated != message:
        return translated
    stripped = message.rstrip("\n")
    if stripped != message:
        stripped_translated = _TRANSLATION.gettext(stripped)
        if stripped_translated != stripped:
            return stripped_translated + message[len(stripped) :]
    return translated


def format_message(message: str, **kwargs: Any) -> str:
    """Translate a format-string template, then interpolate values."""
    return _(message).format(**kwargs)


def _translated_attr(obj: Any, attr: str) -> None:
    value = getattr(obj, attr, None)
    if not value:
        return
    source_attr = f"_cupt_i18n_source_{attr}"
    source = getattr(obj, source_attr, value)
    setattr(obj, source_attr, source)
    setattr(obj, attr, _(source))


def translate_click_metadata(command: Any) -> None:
    """Translate Click command/help metadata after a language is configured."""
    _translated_attr(command, "help")
    _translated_attr(command, "short_help")
    _translated_attr(command, "epilog")

    for param in getattr(command, "params", []):
        _translated_attr(param, "help")
        _translated_attr(param, "prompt")

    for child in getattr(command, "commands", {}).values():
        translate_click_metadata(child)
