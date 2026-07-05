import os
import yaml
from typing import Any, Dict

def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Loads and parses the project YAML configuration file.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at: {config_path}")
        
    with open(config_path, 'r') as file:
        try:
            config = yaml.safe_load(file)
            return config
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error parsing YAML config: {e}")
