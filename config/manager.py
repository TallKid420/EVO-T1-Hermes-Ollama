import os
import yaml

CONFIG_DIR = "config"
SERVICES_YAML = os.path.join(CONFIG_DIR, "services.yaml")
AGENTS_YAML = os.path.join(CONFIG_DIR, "agents.yaml")
PLUGINS_YAML = os.path.join(CONFIG_DIR, "plugins.yaml")

def configs_exist() -> bool:
    return all(os.path.exists(p) for p in [SERVICES_YAML, AGENTS_YAML, PLUGINS_YAML])

def load(path: str) -> dict:
    if os.path.exists(path):
        pass
    elif os.path.exists(os.path.join(CONFIG_DIR, path)):
        path = os.path.join(CONFIG_DIR, path)
    else: return {}
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
    api = cfg.get("api", {})
    flask = cfg.get("flask", {})
    merged_api = dict(api)
    merged_api.update(flask)
    merged_api.update(daemon.get("api", {}))
    merged_api.setdefault("enabled", True)
    merged_api.setdefault("host", "127.0.0.1")
    merged_api.setdefault("port", 5000)
    daemon["api"] = merged_api
    return daemon
