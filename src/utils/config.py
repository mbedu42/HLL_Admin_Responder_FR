import yaml
import os
from typing import Any, Dict
import re

class Config:
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        self.data = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file with environment variable substitution"""
        try:
            with open(self.config_file, 'r') as file:
                content = file.read()
                
            # Replace environment variables in the format ${VAR_NAME}
            def replace_env_var(match):
                var_name = match.group(1)
                return os.getenv(var_name, match.group(0))  # Return original if env var not found
            
            content = re.sub(r'\$\{([^}]+)\}', replace_env_var, content)
            
            config = yaml.safe_load(content)
            print(f"✅ Configuration loaded from {self.config_file}")
            return config
            
        except FileNotFoundError:
            print(f"❌ Configuration file {self.config_file} not found")
            return {}
        except yaml.YAMLError as e:
            print(f"❌ Error parsing YAML configuration: {e}")
            return {}
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'discord.token')"""
        keys = key.split('.')
        value = self.data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        # Handle comma-separated values for admin roles
        if key == 'discord.admin_roles' and isinstance(value, str):
            return [role.strip() for role in value.split(',') if role.strip()]
        
        return value
    
    def __getitem__(self, key: str) -> Any:
        return self.get(key)
    
    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None