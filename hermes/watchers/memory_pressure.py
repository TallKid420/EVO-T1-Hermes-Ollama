try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from hermes.core.severity import Severity, classify_memory_usage
from hermes.watchers.base import BaseWatcher, WatcherResult


class MemoryPressureWatcher(BaseWatcher):
    name = "memory_pressure"

    def __init__(self, warning_pct: float = 90.0, critical_pct: float = 95.0):
        self.warning_pct = warning_pct
        self.critical_pct = critical_pct

    def check(self) -> WatcherResult:
        if not PSUTIL_AVAILABLE:
            return WatcherResult(
                triggered=False,
                severity=Severity.INFO,
                event_type="memory_pressure",
                source="memory_pressure_watcher",
                message="psutil not available — skipping memory check",
                payload={"skipped": True},
            )

        mem = psutil.virtual_memory()
        pct = mem.percent
        severity = classify_memory_usage(pct)
        triggered = severity in (Severity.WARNING, Severity.CRITICAL)

        return WatcherResult(
            triggered=triggered,
            severity=severity,
            event_type="memory_pressure",
            source="memory_pressure_watcher",
            message=f"Memory usage at {pct:.1f}%",
            payload={
                "percent": round(pct, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "total_gb": round(mem.total / 1e9, 2),
                "available_gb": round(mem.available / 1e9, 2),
            },
        )