import yaml
from pathlib import Path


class PermissionError(Exception):
    pass


class ApprovalRequired(Exception):
    pass


class Permissions:
    def __init__(self, config_path="config/autonomy.yaml"):
        self.config = self._load_config(config_path)

    def _load_config(self, path):
        with open(path, "r") as f:
            return yaml.safe_load(f)["autonomous_actions"]

    def check(self, action: str):
        if action not in self.config:
            raise PermissionError(f"Unknown action: {action}")

        policy = self.config[action]

        if not policy.get("allowed", False):
            raise PermissionError(f"Action not allowed: {action}")

        if policy.get("requires_approval", False):
            raise ApprovalRequired(f"Approval required for: {action}")

        return True