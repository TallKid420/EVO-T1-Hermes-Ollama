import os
import yaml

CONFIG_DIR = "config"
SERVICES_YAML = os.path.join(CONFIG_DIR, "services.yaml")
AGENTS_YAML = os.path.join(CONFIG_DIR, "agents.yaml")
PLUGINS_YAML = os.path.join(CONFIG_DIR, "plugins.yaml")

def configs_exist() -> bool:
    return all(os.path.exists(p) for p in [SERVICES_YAML, AGENTS_YAML, PLUGINS_YAML])

def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def save(path: str, data: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def get_daemon_config() -> dict:
    """Reads daemon and API settings from services.yaml."""
    cfg = load(SERVICES_YAML)
    daemon = cfg.get("daemon", {})
    # Ensure API section exists with defaults if not specified
    api = daemon.setdefault("api", {})
    api.setdefault("enabled", True)
    api.setdefault("host", "127.0.0.1")
    api.setdefault("port", 5000)
    return daemon