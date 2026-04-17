from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


def classify_disk_usage(percent: float) -> Severity:
    if percent >= 92:
        return Severity.CRITICAL
    elif percent >= 85:
        return Severity.WARNING
    return Severity.INFO


def classify_memory_usage(percent: float) -> Severity:
    if percent >= 95:
        return Severity.CRITICAL
    elif percent >= 90:
        return Severity.WARNING
    return Severity.INFO


def classify_service_status(is_active: bool, restart_failures: int = 0) -> Severity:
    if not is_active and restart_failures >= 3:
        return Severity.CRITICAL
    elif not is_active:
        return Severity.WARNING
    return Severity.INFO