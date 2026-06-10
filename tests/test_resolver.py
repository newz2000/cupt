"""Tests for cupt.resolver.resolve_task_id — interactive vs non-interactive."""

import pytest

from cupt.resolver import IDResolutionError, resolve_task_id
from cupt.state import StateManager
from cupt.utils import set_interactive_override


@pytest.fixture
def interactive_off():
    set_interactive_override(False)
    yield
    set_interactive_override(None)


@pytest.fixture
def interactive_on():
    set_interactive_override(True)
    yield
    set_interactive_override(None)


@pytest.fixture
def state(tmp_path):
    return StateManager(tmp_path / "state.json")


# ---------------------------------------------------------------------------
# alphanumeric passthrough — same in both modes
# ---------------------------------------------------------------------------


def test_alphanumeric_passes_through_interactive(interactive_on, state):
    assert resolve_task_id("868abc123", state=state) == "868abc123"


def test_alphanumeric_passes_through_non_interactive(interactive_off, state):
    assert resolve_task_id("868abc123", state=state) == "868abc123"


# ---------------------------------------------------------------------------
# short IDs — interactive only
# ---------------------------------------------------------------------------


def test_short_id_resolves_when_interactive(interactive_on, state):
    state.reconcile([{"id": "868target", "name": "T"}])
    assert resolve_task_id("1", state=state) == "868target"


def test_short_id_missing_raises_interactive(interactive_on, state):
    with pytest.raises(IDResolutionError) as exc:
        resolve_task_id("42", state=state)
    assert "No short ID 42" in str(exc.value)


def test_short_id_passes_through_non_interactive(interactive_off, state):
    """Scripts get the literal digits — failure surfaces at the API layer
    rather than silently using whatever short ID the user had set."""
    state.reconcile([{"id": "868target", "name": "T"}])
    assert resolve_task_id("1", state=state) == "1"


# ---------------------------------------------------------------------------
# active task fallback
# ---------------------------------------------------------------------------


def test_no_arg_uses_active_task(interactive_on, state):
    state.set_active("868abc", "Active")
    assert resolve_task_id(None, state=state) == "868abc"
    assert resolve_task_id("", state=state) == "868abc"


def test_no_arg_no_active_raises(interactive_on, state):
    with pytest.raises(IDResolutionError) as exc:
        resolve_task_id(None, state=state)
    assert "No task ID and no active task" in str(exc.value)


def test_no_arg_non_interactive_raises_different_message(interactive_off, state):
    state.set_active("868abc", "Active")  # set it but it must be ignored
    with pytest.raises(IDResolutionError) as exc:
        resolve_task_id(None, state=state)
    assert "non-interactive" in str(exc.value)


def test_allow_active_false_rejects_no_arg(interactive_on, state):
    """`cupt start` passes allow_active=False so you can't accidentally
    'restart' the current active task by typing nothing."""
    state.set_active("868abc", "Active")
    with pytest.raises(IDResolutionError):
        resolve_task_id(None, state=state, allow_active=False)
