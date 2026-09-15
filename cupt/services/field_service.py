"""Business logic for reading and writing ClickUp custom fields.

A task's ``custom_fields`` array (from ``GET /task/{id}``) already carries
every custom field available on that task's list, valued or not. Callers of
this service never see a field's uuid or an option's uuid — they work with
human names and get them back on read.
"""

import logging
from typing import Any, Dict, List, Optional

from cupt.api import ClickUpClient

logger = logging.getLogger(__name__)


def option_label(option: Dict[str, Any]) -> str:
    """An option's display text: ``name`` for most fields, ``label`` for labels."""
    return option.get("name") or option.get("label") or ""


def resolve_option(field: Dict[str, Any], stored: Any) -> Optional[Dict[str, Any]]:
    """Find the option a dropdown/label field's stored value refers to.

    ClickUp stores either the option's uuid or its ``orderindex``, so both are
    matched. Nothing else is: resolving by *position* in the options list was
    tried and removed, because a stored index left over from before an option
    was deleted or reordered would land on an unrelated option and display a
    plausible but wrong name. An unresolvable value returns None, and the
    caller reports it as unset rather than inventing an answer.
    """
    for option in field.get("type_config", {}).get("options", []) or []:
        if option.get("id") == stored or option.get("orderindex") == stored:
            return option
    return None


def display_value(field: Dict[str, Any]) -> Any:
    """The human-readable value of one custom field, or None when unset.

    Canonical for the whole codebase — ``TaskService.field_value`` delegates
    here so display and filtering can never disagree about what a field says.

    A dropdown resolves to its option's name and a label/multi-select to a
    list of option names. A value that resolves to no current option reads as
    None: the raw uuid must never reach a caller (the CLI addresses fields and
    options by name only), and None is the safe direction for a filter, which
    then declines to match rather than matching on an id the user never typed.
    """
    value = field.get("value")
    if value is None:
        return None

    field_type = field.get("type")

    if field_type == "drop_down":
        option = resolve_option(field, value)
        if option is None:
            logger.debug(
                "custom field %r: stored value %r matches no current option",
                field.get("name"),
                value,
            )
            return None
        return option_label(option)

    if field_type in ("labels", "multi_select"):
        if not isinstance(value, list):
            return value
        names = []
        for item in value:
            option = resolve_option(field, item)
            if option is None:
                logger.debug(
                    "custom field %r: stored label %r matches no current option",
                    field.get("name"),
                    item,
                )
                continue
            names.append(option_label(option))
        return names or None

    return value


class FieldService:
    def __init__(self, client: ClickUpClient):
        self.client = client

    def list_fields(self, task_id: str) -> List[Dict[str, Any]]:
        """Return a normalized view of every custom field on ``task_id``.

        Each entry is ``{"id", "name", "type", "value"}`` where ``value`` is
        the human-readable value: a dropdown resolves to its option name (not
        the uuid ClickUp stores), a label/multi-select resolves to a list of
        option names, everything else passes through unchanged, and an unset
        field is ``None``.
        """
        task = self.client.get_task(task_id)
        fields = task.get("custom_fields", []) or []
        return [
            {
                "id": field.get("id"),
                "name": field.get("name"),
                "type": field.get("type"),
                "value": self._display_value(field),
            }
            for field in fields
        ]

    def resolve_field(self, task_id: str, name: str) -> Dict[str, Any]:
        """Find the raw ClickUp field dict whose name matches ``name``.

        Matching is case-insensitive with surrounding whitespace stripped.
        Raises ``ValueError`` naming the unknown field and listing the
        available field names when there is no match.
        """
        task = self.client.get_task(task_id)
        fields = task.get("custom_fields", []) or []
        target = name.strip().lower()
        for field in fields:
            if str(field.get("name", "")).strip().lower() == target:
                return field

        available = ", ".join(str(f.get("name", "")) for f in fields)
        if available:
            raise ValueError(f"Unknown field '{name}'. Available fields: {available}")
        raise ValueError(
            f"Unknown field '{name}'. No custom fields are available on this task."
        )

    def coerce_value(self, field: Dict[str, Any], raw: str) -> Any:
        """Turn a command-line string into the value the API expects.

        Keyed off ``field["type"]``:

        - ``drop_down``: matched case-insensitively against the field's
          options and resolved to the option's uuid. Raises ``ValueError``
          listing the valid option names on no match.
        - ``number``: ``int`` when the string is integral, else ``float``.
          Raises ``ValueError`` on non-numeric input.
        - ``checkbox``: true/false/yes/no/1/0 (case-insensitive) to ``bool``.
          Raises ``ValueError`` on anything else.
        - everything else: the string, unchanged.
        """
        field_type = field.get("type")

        if field_type == "drop_down":
            return self._coerce_dropdown(field, raw)

        if field_type == "number":
            return self._coerce_number(field, raw)

        if field_type == "checkbox":
            return self._coerce_checkbox(field, raw)

        return raw

    def set_field(self, task_id: str, name: str, raw: str) -> Dict[str, Any]:
        """Resolve ``name``, coerce ``raw``, and write it to ``task_id``.

        Returns ``{"field", "value", "display"}`` — ``value`` is what was
        sent to the API, ``display`` is the human string it corresponds to
        (the canonical option name for a dropdown, ``raw`` otherwise).
        """
        field = self.resolve_field(task_id, name)
        value = self.coerce_value(field, raw)
        self.client.set_task_custom_field(task_id, field["id"], value)

        display = raw
        if field.get("type") == "drop_down":
            option = resolve_option(field, value)
            if option is not None:
                display = option_label(option)

        return {"field": field.get("name"), "value": value, "display": display}

    def clear_field(self, task_id: str, name: str) -> Dict[str, Any]:
        """Resolve ``name`` and clear it on ``task_id``. Returns ``{"field"}``."""
        field = self.resolve_field(task_id, name)
        self.client.remove_task_custom_field(task_id, field["id"])
        return {"field": field.get("name")}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _display_value(field: Dict[str, Any]) -> Any:
        """Human-readable form of ``field["value"]``. See :func:`display_value`."""
        return display_value(field)

    def _coerce_dropdown(self, field: Dict[str, Any], raw: str) -> str:
        options = field.get("type_config", {}).get("options", []) or []
        target = raw.strip().lower()
        for option in options:
            if option_label(option).strip().lower() == target:
                return option.get("id")

        valid = ", ".join(option_label(o) for o in options)
        raise ValueError(
            f"Unknown option '{raw}' for field '{field.get('name')}'. "
            f"Valid options: {valid}"
        )

    @staticmethod
    def _coerce_number(field: Dict[str, Any], raw: str) -> Any:
        text = raw.strip()
        body = text[1:] if text[:1] in "+-" else text
        try:
            if body.isdigit():
                return int(text)
            return float(text)
        except ValueError:
            raise ValueError(f"Invalid number for field '{field.get('name')}': '{raw}'")

    @staticmethod
    def _coerce_checkbox(field: Dict[str, Any], raw: str) -> bool:
        text = raw.strip().lower()
        if text in ("true", "yes", "1"):
            return True
        if text in ("false", "no", "0"):
            return False
        raise ValueError(
            f"Invalid checkbox value for field '{field.get('name')}': '{raw}'. "
            "Use true/false, yes/no, or 1/0."
        )
