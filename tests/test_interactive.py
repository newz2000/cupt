"""Tests for cupt.utils.is_interactive — the gate that hides stateful UX
from scripts and subprocesses."""

import pytest

from cupt.utils import is_interactive, set_interactive_override


class _Stream:
    def __init__(self, tty: bool):
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


@pytest.fixture(autouse=True)
def reset_override():
    """Each test starts with no override and clears any it sets."""
    set_interactive_override(None)
    yield
    set_interactive_override(None)


def test_defaults_to_tty(monkeypatch):
    monkeypatch.delenv("CUPT_INTERACTIVE", raising=False)
    monkeypatch.delenv("CI", raising=False)
    assert is_interactive(_Stream(True)) is True
    assert is_interactive(_Stream(False)) is False


def test_override_wins_over_env_and_tty(monkeypatch):
    monkeypatch.setenv("CUPT_INTERACTIVE", "0")
    set_interactive_override(True)
    assert is_interactive(_Stream(False)) is True


def test_env_var_forces_on(monkeypatch):
    monkeypatch.setenv("CUPT_INTERACTIVE", "1")
    assert is_interactive(_Stream(False)) is True


def test_env_var_forces_off(monkeypatch):
    monkeypatch.setenv("CUPT_INTERACTIVE", "0")
    assert is_interactive(_Stream(True)) is False


def test_ci_env_forces_off(monkeypatch):
    """CI runners often have TTY-looking stdout but should still be treated
    as non-interactive so test/release pipelines never touch state.json."""
    monkeypatch.delenv("CUPT_INTERACTIVE", raising=False)
    monkeypatch.setenv("CI", "true")
    assert is_interactive(_Stream(True)) is False


def test_explicit_cupt_interactive_overrides_ci(monkeypatch):
    """Power users can force interactive in CI for debugging if they really
    want to (CUPT_INTERACTIVE has higher precedence than CI=true)."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("CUPT_INTERACTIVE", "1")
    assert is_interactive(_Stream(False)) is True
