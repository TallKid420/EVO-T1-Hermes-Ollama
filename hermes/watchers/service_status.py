import subprocess
import sys

from hermes.core.severity import Severity
from hermes.watchers.base import BaseWatcher, WatcherResult


class ServiceStatusWatcher(BaseWatcher):
    name = "service_status"

    def __init__(self, services: list):
        # services = list of dicts from services.yaml managed_services
        self.services = services

    def _is_active(self, unit: str) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() == "active"
        except FileNotFoundError:
            # systemctl not available (Windows dev machine)
            return True
        except Exception:
            return False

    def check(self) -> WatcherResult:
        failed = []

        for svc in self.services:
            unit = svc["systemd_unit"]
            name = svc["name"]
            if not self._is_active(unit):
                failed.append({"name": name, "unit": unit})

        if not failed:
            return WatcherResult(
                triggered=False,
                severity=Severity.INFO,
                event_type="service_status",
                source="service_status_watcher",
                message="All managed services active",
                payload={"failed": []},
            )

        return WatcherResult(
            triggered=True,
            severity=Severity.CRITICAL,
            event_type="service_unhealthy",
            source="service_status_watcher",
            message=f"Services down: {[s['name'] for s in failed]}",
            payload={"failed": failed, "service": failed[0]["name"]},
        )