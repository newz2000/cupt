import os
import pytest
from pathlib import Path
from cupt.config import ConfigManager

def test_config_initialization(tmp_path):
    config_file = tmp_path / "config.yaml"
    manager = ConfigManager(config_file)
    
    assert config_file.exists()
    config = manager.load_config()
    assert "auth" in config
    assert "user" in config

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
