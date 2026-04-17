import shutil

from hermes.core.severity import Severity, classify_disk_usage
from hermes.watchers.base import BaseWatcher, WatcherResult


class DiskPressureWatcher(BaseWatcher):
    name = "disk_pressure"

    def __init__(self, path: str = "/", warning_pct: float = 85.0, critical_pct: float = 92.0):
        self.path = path
        self.warning_pct = warning_pct
        self.critical_pct = critical_pct

    def check(self) -> WatcherResult:
        usage = shutil.disk_usage(self.path)
        pct = (usage.used / usage.total) * 100
        severity = classify_disk_usage(pct)
        triggered = severity in (Severity.WARNING, Severity.CRITICAL)

        return WatcherResult(
            triggered=triggered,
            severity=severity,
            event_type="disk_pressure",
            source="disk_pressure_watcher",
            message=f"Disk usage at {pct:.1f}%",
            payload={
                "path": self.path,
                "used_gb": round(usage.used / 1e9, 2),
                "total_gb": round(usage.total / 1e9, 2),
                "percent": round(pct, 2),
            },
        )