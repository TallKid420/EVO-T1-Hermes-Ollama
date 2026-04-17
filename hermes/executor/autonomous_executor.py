import subprocess

from hermes.core.permissions import Permissions, PermissionError, ApprovalRequired
from hermes.core.cooldowns import CooldownManager
from hermes.core.safety import SafetyManager
from hermes.utils.logging import Logger


class AutonomousExecutor:
    def __init__(self, services_config):
        self.permissions = Permissions()
        self.cooldowns = CooldownManager()
        self.safety = SafetyManager()
        self.logger = Logger()

        self.services = {
            s["name"]: s for s in services_config["managed_services"]
        }

    def _run_command(self, command: list):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return -1, "", str(e)

    def restart_service(self, service_name: str):
        action_key = f"restart:{service_name}"

        if service_name not in self.services:
            raise PermissionError(f"Service not allowed: {service_name}")

        service = self.services[service_name]

        # Permission check
        self.permissions.check("restart_service")

        # Cooldown check
        if not self.cooldowns.can_execute(action_key, service["cooldown_seconds"]):
            return {"status": "cooldown_blocked"}

        # Rate limit check
        if self.cooldowns.count_recent(action_key, 3600) >= service["max_restarts_per_hour"]:
            self.logger.event(
                f"Restart limit exceeded for {service_name}", "critical"
            )
            return {"status": "rate_limited"}

        # Execute
        code, out, err = self._run_command(
            ["systemctl", "restart", service["systemd_unit"]]
        )

        success = code == 0

        self.cooldowns.record(action_key)

        self.logger.action(
            action="restart_service",
            service=service_name,
            result=out if success else err,
            success=success,
        )

        return {
            "status": "success" if success else "failed",
            "output": out,
            "error": err,
        }

    def cleanup_path(self, path: str):
        self.permissions.check("cleanup_cache")
        self.safety.validate_path(path)

        code, out, err = self._run_command(["rm", "-rf", path])

        success = code == 0

        self.logger.action(
            action="cleanup_path",
            result=out if success else err,
            success=success,
            metadata={"path": path},
        )

        return {"status": "success" if success else "failed"}