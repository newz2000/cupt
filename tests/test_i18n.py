"""Tests for text-only gettext catalog loading."""

from cupt.i18n import _, configure_language


def test_configure_language_loads_spanish_po_catalog():
    configure_language("es")
    assert _("CUPT - ClickUp Task Management CLI") == (
        "CUPT - CLI de gestión de tareas de ClickUp"
    )


def test_configure_language_falls_back_for_missing_catalog():
    configure_language("zz")
    assert (
        _("CUPT - ClickUp Task Management CLI") == "CUPT - ClickUp Task Management CLI"
    )
