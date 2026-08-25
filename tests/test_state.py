"""Tests for cupt.state.StateManager — short IDs + active task persistence."""

import json

import pytest

from cupt.state import StateManager

# ---------------------------------------------------------------------------
# active task
# ---------------------------------------------------------------------------


def test_state_empty_when_file_missing(tmp_path):
    """A fresh install reads as empty without writing anything to disk."""
    sm = StateManager(tmp_path / "state.json")
    assert sm.get_active() is None
    assert sm.short_id_map() == {}
    assert not (tmp_path / "state.json").exists()


def test_set_active_persists_clickup_id_and_name(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    previous = sm.set_active("868abc", "Fix login")
    assert previous is None
    active = sm.get_active()
    assert active["clickup_id"] == "868abc"
    assert active["name"] == "Fix login"
    assert "started_at" in active

    # Second instance reads from disk.
    sm2 = StateManager(tmp_path / "state.json")
    assert sm2.get_active()["clickup_id"] == "868abc"


def test_set_active_returns_previous(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.set_active("868abc", "First")
    previous = sm.set_active("868def", "Second")
    assert previous["clickup_id"] == "868abc"
    assert sm.get_active()["clickup_id"] == "868def"


def test_clear_active_only_if_id_matches(tmp_path):
    """`cupt done X` should not clear active if active is a different task."""
    sm = StateManager(tmp_path / "state.json")
    sm.set_active("868abc", "Active task")
    cleared = sm.clear_active(only_if_id="868def")
    assert cleared is None
    assert sm.get_active()["clickup_id"] == "868abc"

    cleared = sm.clear_active(only_if_id="868abc")
    assert cleared["clickup_id"] == "868abc"
    assert sm.get_active() is None


def test_clear_active_no_op_when_none(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    assert sm.clear_active() is None


# ---------------------------------------------------------------------------
# short ID reconciliation
# ---------------------------------------------------------------------------


def _task(tid, name="T"):
    return {"id": tid, "name": name}


def test_reconcile_assigns_lowest_free_int(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    mapping = sm.reconcile([_task("868a"), _task("868b"), _task("868c")])
    assert mapping == {"868a": "1", "868b": "2", "868c": "3"}


def test_reconcile_full_sync_frees_missing(tmp_path):
    """Full sync (e.g. unfiltered `cupt list`) drops short IDs whose tasks
    are no longer in the pending set, freeing those ints for reuse."""
    sm = StateManager(tmp_path / "state.json")
    sm.reconcile([_task("868a"), _task("868b"), _task("868c")])
    mapping = sm.reconcile([_task("868a"), _task("868c")], full_sync=True)
    assert mapping == {"868a": "1", "868c": "3"}

    # The freed slot 2 is now available to a new task.
    mapping = sm.reconcile(
        [_task("868a"), _task("868c"), _task("868d")], full_sync=True
    )
    assert mapping["868d"] == "2"


def test_reconcile_additive_keeps_old_entries(tmp_path):
    """Filtered lists (today/overdue/week) should NOT free unrelated IDs —
    those tasks are still pending, just not in this view."""
    sm = StateManager(tmp_path / "state.json")
    sm.reconcile([_task("868a"), _task("868b")], full_sync=True)
    # Filtered view only shows one task; the other must keep its short ID.
    sm.reconcile([_task("868a")], full_sync=False)
    assert sm.short_id_for("868b") == "2"


def test_reconcile_refreshes_cached_name(tmp_path):
    """Renaming a task in ClickUp should propagate to the footer cache."""
    sm = StateManager(tmp_path / "state.json")
    sm.reconcile([_task("868a", name="Old")])
    sm.reconcile([_task("868a", name="New")])
    entry = sm.lookup_short(1)
    assert entry["name"] == "New"


def test_lookup_short_returns_entry(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    sm.reconcile([_task("868abc", name="Hello")])
    assert sm.lookup_short(1)["clickup_id"] == "868abc"
    assert sm.lookup_short(99) is None


def test_free_short_for_removes_entry(tmp_path):
    """`cupt done` calls this to free the slot immediately."""
    sm = StateManager(tmp_path / "state.json")
    sm.reconcile([_task("868a"), _task("868b")])
    freed = sm.free_short_for("868a")
    assert freed == "1"
    assert sm.lookup_short(1) is None
    # Subsequent reconciliation reclaims the freed slot.
    mapping = sm.reconcile([_task("868b"), _task("868c")], full_sync=True)
    assert mapping["868c"] == "1"


def test_free_short_for_unknown_id_is_noop(tmp_path):
    sm = StateManager(tmp_path / "state.json")
    assert sm.free_short_for("nope") is None


# ---------------------------------------------------------------------------
# corruption / version handling
# ---------------------------------------------------------------------------


def test_corrupt_state_file_resets_to_empty(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text("{not json")
    sm = StateManager(state_file)
    assert sm.get_active() is None
    assert sm.short_id_map() == {}


def test_version_mismatch_resets_to_empty(tmp_path):
    state_file = tmp_path / "state.json"
    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text(json.dumps({"version": 999, "active_task": {"x": 1}}))
    sm = StateManager(state_file)
    assert sm.get_active() is None


def test_save_is_atomic(tmp_path):
    """Tempfile is cleaned up; final file ends up at the expected path."""
    sm = StateManager(tmp_path / "state.json")
    sm.set_active("868a", "Test")
    # No stray .state.* tempfiles left behind.
    leftovers = list(tmp_path.glob(".state.*.tmp"))
    assert leftovers == []
    assert (tmp_path / "state.json").exists()


# ---------------------------------------------------------------------------
# CUPT_HOME — multi-account isolation
# ---------------------------------------------------------------------------


def test_state_defaults_to_home_dot_cupt(monkeypatch, tmp_path):
    monkeypatch.delenv("CUPT_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert StateManager().state_file == tmp_path / ".cupt" / "state.json"


def test_state_follows_cupt_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CUPT_HOME", str(tmp_path / "work"))
    assert StateManager().state_file == tmp_path / "work" / "state.json"


def test_active_task_does_not_leak_between_cupt_homes(monkeypatch, tmp_path):
    """The active task is per-account: starting a task under one CUPT_HOME
    must be invisible to another."""
    monkeypatch.setenv("CUPT_HOME", str(tmp_path / "work"))
    StateManager().set_active("868abc", "Work task")

    monkeypatch.setenv("CUPT_HOME", str(tmp_path / "personal"))
    assert StateManager().get_active() is None

    monkeypatch.setenv("CUPT_HOME", str(tmp_path / "work"))
    assert StateManager().get_active()["clickup_id"] == "868abc"
