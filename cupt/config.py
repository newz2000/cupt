"""
Configuration management for CUPT CLI
"""

import json
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path:
            self.config_file = config_path
            self.config_dir = self.config_file.parent
        else:
            self.config_dir = Path.home() / ".cupt"
            self.config_file = self.config_dir / "config.yaml"

        self.cache_file = self.config_dir / "parent_cache.json"
        self._config: Optional[Dict[str, Any]] = None  # in-memory cache; valid for lifetime of this instance

        self.config_dir.mkdir(exist_ok=True, parents=True)

        if not self.config_file.exists():
            self._create_default_config()

    def _create_default_config(self):
        """Create default configuration file"""
        default_config = {
            "auth": {
                "access_token": None,
                "refresh_token": None,
                "expires_at": None,
                "client_id": None,
                "client_secret": None,
            },
            "user": {
                "team_id": None,
                "user_id": None,
                "default_list_id": None,
            },
            "cache": {
                "last_sync": None,
                "tasks_ttl": 300,
            },
        }
        with open(self.config_file, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)
        os.chmod(self.config_file, 0o600)

    def load_config(self) -> Dict[str, Any]:
        """Load configuration, using in-memory cache to avoid repeated disk reads."""
        if self._config is None:
            with open(self.config_file, "r") as f:
                self._config = yaml.safe_load(f) or {}
        return self._config

    def save_config(self, config: Dict[str, Any]):
        """Persist configuration and refresh the in-memory cache."""
        self._config = config
        with open(self.config_file, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        os.chmod(self.config_file, 0o600)

    def get(self, key: str, default=None):
        """Get a dot-separated configuration value."""
        config = self.load_config()
        value = config
        for k in key.split("."):
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        """Set a dot-separated configuration value."""
        config = self.load_config()
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
        with open(self.cache_file, "w") as f:
            json.dump(cache_data, f)
        os.chmod(self.cache_file, 0o600)

    def clear_cache(self):
        """Delete the persistent cache file."""
        if self.cache_file.exists():
            self.cache_file.unlink()
