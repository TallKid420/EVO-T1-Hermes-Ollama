import yaml
from enum import IntEnum
from typing import Dict, Any, List

class RiskLevel(IntEnum):
    LOW = 1      # Auto-run without asking
    MEDIUM = 2   # Auto-run but log/notify
    HIGH = 3     # BLOCK: Wait for manual approval (hermesctl tasks approve)

class SafetyManager:
    def __init__(self, 
                 fs_config="config/filesystem.yaml", 
                 autonomy_config="config/autonomy.yaml"):
        self.fs_config = self._load_config(fs_config)
        self.autonomy_config = self._load_config(autonomy_config)
        
        self.safe_paths = self.fs_config.get("safe_paths", [])
        self.restricted_paths = self.fs_config.get("restricted_paths", [])
        
        # Risk levels for task types
        self.task_risks = self.autonomy_config.get("task_risks", {})
        # Exact command prefixes allowed in shell
        self.allowed_commands = self.autonomy_config.get("allowed_commands", [])
        # Allowed plugin permission scopes and runtime registration map
        self.allowed_plugin_permissions = set(
            self.autonomy_config.get(
                "plugin_permissions",
                ["filesystem", "sql", "network", "notifications", "system"],
            )
        )
        self.plugin_permission_registry: Dict[str, List[str]] = {}

    def _load_config(self, path):
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    # --- Path Safety (Existing) ---
    def is_safe_path(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.safe_paths)

    def is_restricted_path(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.restricted_paths)

    def validate_path(self, path: str):
        if self.is_restricted_path(path):
            raise PermissionError(f"Restricted path: {path}")
        if not self.is_safe_path(path):
            raise PermissionError(f"Path not in safe allowlist: {path}")
        return True

    # --- Action Safety (New) ---
    def get_risk_level(self, task_type: str) -> RiskLevel:
        lvl = self.task_risks.get(task_type, "HIGH") # Default to HIGH safety
        return RiskLevel[lvl]

    def validate_command(self, cmd_str: str):
        """Checks if a shell command starts with an approved prefix."""
        if any(cmd_str.startswith(allowed) for allowed in self.allowed_commands):
            return True
        raise PermissionError(f"Command not in allowlist: {cmd_str}")

    # --- Plugin Permission Safety ---
    def check_plugin_permissions(self, required_permissions: List[str]) -> bool:
        unknown = [
            p
            for p in required_permissions
            if str(p).strip().lower() not in self.allowed_plugin_permissions
        ]
        if unknown:
            raise PermissionError(f"Unknown or disallowed plugin permissions: {unknown}")
        return True

    def register_plugin_permissions(self, plugin_name: str, required_permissions: List[str]) -> bool:
        normalized = [str(p).strip().lower() for p in required_permissions]
        self.check_plugin_permissions(normalized)
        self.plugin_permission_registry[plugin_name] = normalized
        return True