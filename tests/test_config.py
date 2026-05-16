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
    manager.set("user.team_id", "abc")

    assert config_file.exists()
    config = manager.load_config()
    assert config["user"]["team_id"] == "abc"


def test_config_set_get(tmp_path):
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)

    manager.set("user.team_id", "12345")
    assert manager.get("user.team_id") == "12345"

    # Nested set
    manager.set("auth.access_token", "secret")
    assert manager.get("auth.access_token") == "secret"


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
