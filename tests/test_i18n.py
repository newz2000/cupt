"""Tests for text-only gettext catalog loading."""

import pytest
from click.testing import CliRunner

from cupt.i18n import _, configure_language
from cupt.main import cli


def test_configure_language_loads_latin_american_spanish_po_catalog():
    selected = configure_language("es_LA")
    assert selected == "es_LA"
    assert _("CUPT - ClickUp Task Management CLI") == (
        "CUPT - CLI de gestión de tareas de ClickUp"
    )


def test_configure_language_aliases_generic_spanish_to_latin_america():
    selected = configure_language("es")

    assert selected == "es_LA"
    assert _("CUPT - ClickUp Task Management CLI") == (
        "CUPT - CLI de gestión de tareas de ClickUp"
    )


def test_configure_language_aliases_portuguese_brazil_hyphen_form():
    selected = configure_language("pt-BR")

    assert selected == "pt_BR"
    assert _("List tasks with optional filters") == (
        "Listar tarefas com filtros opcionais"
    )


def test_configure_language_falls_back_to_supported_base_locale():
    selected = configure_language("fr-FR")

    assert selected == "fr"
    assert _("List tasks with optional filters") == (
        "Lister les tâches avec des filtres optionnels"
    )


def test_configure_language_falls_back_for_missing_catalog():
    configure_language("zz")
    assert (
        _("CUPT - ClickUp Task Management CLI") == "CUPT - ClickUp Task Management CLI"
    )


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("es", "Listar tareas con filtros opcionales"),
        ("es_ES", "Listar tareas con filtros opcionales"),
        ("fr", "Lister les tâches avec des filtres optionnels"),
        ("de", "Aufgaben mit optionalen Filtern auflisten"),
        ("it", "Elencare attività con filtri opzionali"),
        ("pt_BR", "Listar tarefas com filtros opcionais"),
    ],
)
def test_help_translates_command_metadata_for_beta_catalogs(locale, expected):
    result = CliRunner().invoke(cli, ["--lang", locale, "list", "--help"])

    assert result.exit_code == 0
    assert expected in result.output


def test_language_can_return_to_english_after_spanish_help():
    runner = CliRunner()

    spanish = runner.invoke(cli, ["--lang", "es", "list", "--help"])
    english = runner.invoke(cli, ["--lang", "en", "list", "--help"])

    assert spanish.exit_code == 0
    assert english.exit_code == 0
    assert "Listar tareas con filtros opcionales" in spanish.output
    assert "List tasks with optional filters" in english.output
