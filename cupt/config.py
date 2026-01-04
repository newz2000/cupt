"""
Configuration management for CUPT CLI (simplified version)
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigManager:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path:
            self.config_file = config_path
            self.config_dir = self.config_file.parent
        else:
            self.config_dir = Path.home() / ".cupt"
            self.config_file = self.config_dir / "config.yaml"
            
        self.config_dir.mkdir(exist_ok=True, parents=True)
        
        # Ensure config file exists
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
                "client_secret": None
            },
            "user": {
                "team_id": None,
                "user_id": None,
                "default_list_id": None
            },
            "cache": {
                "last_sync": None,
                "tasks_ttl": 300  # 5 minutes
            }
        }
        
        with open(self.config_file, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False)
        
        # Set proper file permissions
        os.chmod(self.config_file, 0o600)
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        with open(self.config_file, 'r') as f:
            return yaml.safe_load(f) or {}
    
    def save_config(self, config: Dict[str, Any]):
        """Save configuration to file"""
        with open(self.config_file, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        # Ensure proper permissions
        os.chmod(self.config_file, 0o600)
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        config = self.load_config()
        keys = key.split('.')
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        config = self.load_config()
        keys = key.split('.')
        current = config
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
        self.save_config(config)
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated"""
        token = self.get('auth.access_token')
        return token is not None and len(token) > 0