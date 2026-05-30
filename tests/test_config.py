import os
from pathlib import Path

import pytest

from cupt.config import ConfigManager


def test_config_lazy_initialization(tmp_path):
    """Constructing a ConfigManager must not touch disk — library users
    importing cupt shouldn't get a config dir carved into their home."""
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)

    assert not config_file.exists()
    # Reads of a missing config return empty defaults, no file gets created.
    assert manager.load_config() == {}
    assert not config_file.exists()


def test_config_created_on_first_write(tmp_path):
    """First write materializes the directory and persists the value."""
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)
    manager.set("user.workspace_id", "abc")

    assert config_file.exists()
    config = manager.load_config()
    assert config["user"]["workspace_id"] == "abc"


def test_config_set_get(tmp_path):
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)

    manager.set("user.workspace_id", "12345")
    assert manager.get("user.workspace_id") == "12345"

    # Nested set
    manager.set("auth.access_token", "secret")
    assert manager.get("auth.access_token") == "secret"


def test_workspace_id_legacy_fallback(tmp_path):
    """Configs written before the team→workspace rename (pre-0.7) still work.

    `user.team_id` was the old key for the workspace. New code reads
    `user.workspace_id`; the fallback prevents existing installs from
    needing to re-run `cupt auth` after upgrading.
    """
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)
    manager.set("user.team_id", "legacy_ws")  # only the old key exists
    assert manager.get("user.workspace_id") == "legacy_ws"


def test_is_authenticated(tmp_path):
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)

    assert not manager.is_authenticated()

    manager.set("auth.access_token", "pk_123")
    assert manager.is_authenticated()


def test_save_load_task_detail(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    data = {"task": {"id": "t1", "name": "Test"}, "comments": [], "cached_at": 1.0}

    manager.save_task_detail("t1", data)
    loaded = manager.load_task_detail("t1")

    assert loaded is not None
    assert loaded["task"]["name"] == "Test"
    assert loaded["cached_at"] == 1.0


def test_load_task_detail_missing(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    assert manager.load_task_detail("nonexistent") is None


def test_task_cache_dir_created_lazily(tmp_path):
    """Cache dir is only created when the first write happens, not on init."""
    manager = ConfigManager(tmp_path / "config.yaml")
    assert not manager.task_cache_dir.exists()
    manager.save_task_detail("t1", {"task": {}, "cached_at": 1.0})
    assert manager.task_cache_dir.is_dir()


def test_top_level_library_imports():
    """`from cupt import ...` must expose the documented public API."""
    from cupt import (
        APIError,
        AuthError,
        ClickUpClient,
        ConfigError,
        CuptError,
        NoteService,
        TaskService,
        TimeService,
    )

    # Spot-check: instantiating the client does no I/O and needs only a token.
    client = ClickUpClient("pk_fake")
    assert hasattr(client, "get_task")
    assert TaskService(client).client is client


def test_clear_cache_removes_task_details(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.save_task_detail("t1", {"task": {}, "cached_at": 1.0})
    manager.save_task_detail("t2", {"task": {}, "cached_at": 1.0})

    assert manager.load_task_detail("t1") is not None
    manager.clear_cache()
    assert manager.load_task_detail("t1") is None
    assert manager.load_task_detail("t2") is None


# ---------------------------------------------------------------------------
# Config load / read
# ---------------------------------------------------------------------------


def test_load_config_reads_existing_file_after_fresh_instance(tmp_path):
    """A new ConfigManager pointed at an existing file lazily reads it."""
    config_file = tmp_path / "config.yaml"
    ConfigManager(config_file).set("user.workspace_id", "abc")

    fresh = ConfigManager(config_file)
    assert fresh._config is None  # not loaded yet
    assert fresh.get("user.workspace_id") == "abc"
    assert fresh._config is not None  # populated by the read


def test_get_missing_key_returns_default(tmp_path):
    """Non-existent keys return the supplied default, not None."""
    manager = ConfigManager(tmp_path / "config.yaml")
    assert manager.get("does.not.exist", default="fallback") == "fallback"


def test_raw_get_returns_none_for_missing_key(tmp_path):
    """_raw_get bypasses the legacy fallback and returns None on miss.

    Guards the fallback path in `get` from infinite recursion when neither
    `user.workspace_id` nor the legacy `user.team_id` is set.
    """
    manager = ConfigManager(tmp_path / "config.yaml")
    assert manager._raw_get("user.team_id") is None
    # And the public `get` returns the default rather than recursing forever.
    assert manager.get("user.workspace_id", default="none") == "none"


# ---------------------------------------------------------------------------
# Parent-name cache (load / save / corruption)
# ---------------------------------------------------------------------------


def test_save_and_load_parent_cache_roundtrip(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.save_cache({"p1": "Parent One", "p2": "Parent Two"})
    assert manager.load_cache() == {"p1": "Parent One", "p2": "Parent Two"}


def test_load_cache_missing_file_returns_empty(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    assert manager.load_cache() == {}


def test_load_cache_corrupted_file_returns_empty(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._ensure_dirs()
    manager.cache_file.write_text("this is not json {{{")
    assert manager.load_cache() == {}


# ---------------------------------------------------------------------------
# Task list cache (load / save / corruption / write failures)
# ---------------------------------------------------------------------------


def test_save_and_load_task_cache_roundtrip(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    payload = {"tasks": [{"id": "t1"}], "workspace_id": "ws1", "timestamp": 123.4}
    manager.save_task_cache(payload)
    assert manager.load_task_cache() == payload


def test_load_task_cache_missing_returns_none(tmp_path):
    """The list view treats `None` as 'no cache available' — must not raise."""
    manager = ConfigManager(tmp_path / "config.yaml")
    assert manager.load_task_cache() is None


def test_load_task_cache_corrupted_returns_none(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._ensure_dirs()
    manager.task_cache_file.write_text("{not valid json")
    assert manager.load_task_cache() is None


def test_save_task_cache_swallows_write_failure(tmp_path, caplog):
    """If disk write fails, log a warning but don't propagate — the offline
    cache is best-effort and must never crash the foreground command."""
    import logging

    manager = ConfigManager(tmp_path / "config.yaml")
    # Point the cache file at a path that can't be opened for writing
    # (a directory exists where the file should be).
    manager._ensure_dirs()
    manager.task_cache_file.mkdir()  # now opening as a file will EISDIR

    with caplog.at_level(logging.WARNING, logger="cupt.config"):
        manager.save_task_cache({"tasks": []})

    assert any("task list cache" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task detail cache (corruption / write failures)
# ---------------------------------------------------------------------------


def test_load_task_detail_corrupted_returns_none(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._ensure_dirs()
    manager.task_cache_dir.mkdir(exist_ok=True)
    (manager.task_cache_dir / "t1.json").write_text("{not json")
    assert manager.load_task_detail("t1") is None


def test_save_task_detail_swallows_write_failure(tmp_path, caplog):
    """Same best-effort guarantee for per-task detail writes."""
    import logging

    manager = ConfigManager(tmp_path / "config.yaml")
    manager._ensure_dirs()
    # Pre-create a directory where the per-task file should live.
    (manager.task_cache_dir / "t1.json").mkdir()

    with caplog.at_level(logging.WARNING, logger="cupt.config"):
        manager.save_task_detail("t1", {"task": {}, "cached_at": 1.0})

    assert any("task detail cache" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# clear_cache covers all three artifact families
# ---------------------------------------------------------------------------


def test_clear_cache_removes_list_and_parent_caches(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.save_cache({"p1": "Parent"})
    manager.save_task_cache({"tasks": [], "timestamp": 0})

    assert manager.cache_file.exists()
    assert manager.task_cache_file.exists()

    manager.clear_cache()

    assert not manager.cache_file.exists()
    assert not manager.task_cache_file.exists()


def test_clear_cache_is_safe_when_nothing_exists(tmp_path):
    """Calling clear_cache on a brand-new install must not crash."""
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.clear_cache()  # should be a no-op, no exception
