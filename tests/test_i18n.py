"""Tests for text-only gettext catalog loading."""

from click.testing import CliRunner

from cupt.i18n import _, configure_language
from cupt.main import cli


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


def test_spanish_help_translates_command_metadata():
    result = CliRunner().invoke(cli, ["--lang", "es", "list", "--help"])

    assert result.exit_code == 0
    assert "Listar tareas con filtros opcionales" in result.output
    assert "Mostrar tareas vencidas" in result.output


def test_language_can_return_to_english_after_spanish_help():
    runner = CliRunner()

    spanish = runner.invoke(cli, ["--lang", "es", "list", "--help"])
    english = runner.invoke(cli, ["--lang", "en", "list", "--help"])

    assert spanish.exit_code == 0
    assert english.exit_code == 0
    assert "Listar tareas con filtros opcionales" in spanish.output
    assert "List tasks with optional filters" in english.output
