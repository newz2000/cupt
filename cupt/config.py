"""
Configuration management for CUPT CLI
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


def cupt_home() -> Path:
    """Return the directory holding config, caches, and interactive state.

    Defaults to ``~/.cupt``. Setting ``CUPT_HOME`` points every one of those
    files somewhere else, which is how a single install keeps several ClickUp
    accounts apart — each home carries its own token, default workspace,
    caches, and active task.

    Resolved per call, not at import time, so a caller can set the variable
    before constructing a manager. An empty value means "unset".
    """
    override = os.environ.get("CUPT_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cupt"


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path:
            self.config_file = config_path
            self.config_dir = self.config_file.parent
        else:
            self.config_dir = cupt_home()
            self.config_file = self.config_dir / "config.yaml"

        self.cache_file = self.config_dir / "parent_cache.json"
        self.task_cache_file = self.config_dir / "tasks_cache.json"
        self._config: Optional[Dict[str, Any]] = (
            None  # in-memory cache; invalidated when the file changes on disk
        )
        self._signature: Optional[Tuple[int, int]] = None

        self.task_cache_dir = self.config_dir / "task_cache"

    def _ensure_dirs(self):
        """Create config + cache dirs on demand. Idempotent."""
        self.config_dir.mkdir(exist_ok=True, parents=True)
        self.task_cache_dir.mkdir(exist_ok=True)

    def _file_signature(self) -> Optional[Tuple[int, int]]:
        """``(mtime_ns, size)`` for the config file, or None if absent."""
        try:
            stat = self.config_file.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """Load configuration, caching until the file changes underneath us.

        The cache used to last the lifetime of the instance, which quietly
        broke whenever two managers pointed at one file: the second would save
        a snapshot taken before the first's write and erase it. That cost the
        OAuth flow its access token on every sign-in. Comparing the file's
        (mtime, size) makes a stale read cheap to detect and impossible to act
        on. ``force_reload`` skips the comparison for read-modify-write callers,
        where timestamp granularity is too coarse to rely on.
        """
        signature = self._file_signature()
        if (
            not force_reload
            and self._config is not None
            and signature == self._signature
        ):
            return self._config

        if signature is None:
            # No config on disk yet — return an empty mapping rather than
            # creating one. Library users importing the package shouldn't get a
            # config dir carved into their home unless they actually write
            # something.
            self._config = {}
            self._signature = None
            return self._config

        with open(self.config_file, "r") as f:
            self._config = yaml.safe_load(f) or {}
        self._signature = signature
        return self._config

    def save_config(self, config: Dict[str, Any]):
        """Persist configuration and refresh the in-memory cache."""
        self._ensure_dirs()
        self._config = config
        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        os.chmod(self.config_file, 0o600)
        # Record what we just wrote so the next read trusts the cache.
        self._signature = self._file_signature()

    def get(self, key: str, default=None):
        """Get a dot-separated configuration value."""
        config = self.load_config()
        value = config
        for k in key.split("."):
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                # Legacy fallback for configs written before the team→workspace
                # rename (pre-0.7). Lets existing installs keep working without
                # re-running `cupt auth`.
                if key == "user.workspace_id":
                    legacy = self._raw_get("user.team_id")
                    if legacy is not None:
                        return legacy
                return default
        return value

    def _raw_get(self, key: str):
        """Lookup without the legacy fallback — used internally to avoid recursion."""
        value = self.load_config()
        for k in key.split("."):
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        return value

    def set(self, key: str, value: Any):
        """Set a dot-separated configuration value.

        Always re-reads first: this is a read-modify-write of the whole file,
        so anything another manager wrote since must survive even when both
        writes land inside one filesystem timestamp tick.
        """
        config = self.load_config(force_reload=True)
        current = config
        keys = key.split(".")
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self.save_config(config)

    def is_authenticated(self) -> bool:
        token = self.get("auth.access_token")
        return token is not None and len(token) > 0

    def load_cache(self) -> Dict[str, Any]:
        """Load persistent parent-name cache from JSON file."""
        if not self.cache_file.exists():
            return {}
        try:
            with open(self.cache_file, "r") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_cache(self, cache_data: Dict[str, Any]):
        """Persist parent-name cache to JSON file."""
        self._ensure_dirs()
        with open(self.cache_file, "w") as f:
            json.dump(cache_data, f)
        os.chmod(self.cache_file, 0o600)

    def clear_cache(self):
        """Delete all persistent cache files (parent names, task list, task details)."""
        if self.cache_file.exists():
            self.cache_file.unlink()
        if self.task_cache_file.exists():
            self.task_cache_file.unlink()
        for f in self.task_cache_dir.glob("*.json"):
            f.unlink()

    def save_task_cache(self, data: Dict[str, Any]) -> None:
        """Persist task list cache to disk (used for --offline mode)."""
        try:
            self._ensure_dirs()
            with open(self.task_cache_file, "w") as f:
                json.dump(data, f)
            os.chmod(self.task_cache_file, 0o600)
        except Exception as e:
            logger.warning("Failed to write task list cache: %s", e)

    def save_task_detail(self, task_id: str, data: Dict[str, Any]) -> None:
        """Persist full task detail (task, parent, comments) to a per-task JSON file."""
        try:
            self._ensure_dirs()
            path = self.task_cache_dir / f"{task_id}.json"
            with open(path, "w") as f:
                json.dump(data, f)
            os.chmod(path, 0o600)
        except Exception as e:
            logger.warning("Failed to write task detail cache for %s: %s", task_id, e)

    def load_task_detail(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Load cached task detail. Returns None if missing or unreadable."""
        path = self.task_cache_dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def load_task_cache(self) -> Optional[Dict[str, Any]]:
        """Load task list cache from disk. Returns None if missing or unreadable."""
        if not self.task_cache_file.exists():
            return None
        try:
            with open(self.task_cache_file, "r") as f:
                return json.load(f)
        except Exception:
            return None
