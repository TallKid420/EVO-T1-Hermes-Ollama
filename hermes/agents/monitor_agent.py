"""
MonitorAgent — wraps the standard Hermes watchers and produces a structured
system-status snapshot.

Usage
-----
    agent = MonitorAgent(watchers)
    status = agent.get_status()   # Returns a SystemStatus dict

The returned dict is the canonical shape for Planner.plan(system_status=...).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import yaml

from hermes.watchers.base import BaseWatcher, WatcherResult
from hermes.watchers.ollama_health import OllamaHealthWatcher
from hermes.watchers.disk_pressure import DiskPressureWatcher
from hermes.watchers.memory_pressure import MemoryPressureWatcher
from hermes.watchers.service_status import ServiceStatusWatcher
from hermes.core.severity import Severity

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class WatcherSummary:
    """One watcher's contribution to the system status snapshot."""
    name: str
    healthy: bool
    severity: str         # "info" | "warning" | "critical"
    message: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemStatus:
    """Full system snapshot returned by MonitorAgent.get_status()."""
    overall_healthy: bool
    overall_severity: str               # worst severity across all watchers
    watchers: List[WatcherSummary]      # one entry per registered watcher
    alerts: List[WatcherSummary]        # subset where healthy=False
    summary_text: str                   # human/LLM-readable one-liner

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class MonitorAgent:
    """
    Runs every registered watcher and assembles a SystemStatus snapshot.

    Parameters
    ----------
    watchers:
        List of BaseWatcher instances (the same list passed to HermesDaemon).
    """

    # Severity rank used to pick the worst overall level
    _SEVERITY_RANK: Dict[str, int] = {
        "info": 0,
        "warning": 1,
        "critical": 2,
    }

    def __init__(self, watchers: List[BaseWatcher]) -> None:
        self.watchers = watchers

    @classmethod
    def from_config(
        cls,
        services_config_path: str = "config/services.yaml",
        ollama_url: str = "http://localhost:11434",
    ) -> "MonitorAgent":
        """Build a MonitorAgent that instantiates its own standard watchers from config files."""
        import sys
        with open(services_config_path, "r") as f:
            services_cfg = yaml.safe_load(f) or {}
        services = services_cfg.get("managed_services", [])
        disk_path = "/" if sys.platform != "win32" else "C:\\"
        watchers: List[BaseWatcher] = [
            OllamaHealthWatcher(url=ollama_url, timeout=5),
            DiskPressureWatcher(path=disk_path),
            MemoryPressureWatcher(),
            ServiceStatusWatcher(services=services),
        ]
        return cls(watchers)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_status(self) -> SystemStatus:
        """
        Run all watchers once and return the aggregated SystemStatus.

        Watcher exceptions are caught; a failing watcher is surfaced as a
        CRITICAL alert rather than crashing the agent.
        """
        watcher_summaries: List[WatcherSummary] = []

        for watcher in self.watchers:
            summary = self._run_watcher(watcher)
            watcher_summaries.append(summary)

        alerts = [w for w in watcher_summaries if not w.healthy]
        overall_severity = self._worst_severity(watcher_summaries)
        overall_healthy = overall_severity == "info"

        summary_text = self._build_summary_text(
            overall_healthy, overall_severity, alerts
        )

        return SystemStatus(
            overall_healthy=overall_healthy,
            overall_severity=overall_severity,
            watchers=watcher_summaries,
            alerts=alerts,
            summary_text=summary_text,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_watcher(self, watcher: BaseWatcher) -> WatcherSummary:
        try:
            result: WatcherResult = watcher.check()
            severity_str = self._severity_to_str(result.severity)
            return WatcherSummary(
                name=watcher.name,
                healthy=not result.triggered,
                severity=severity_str,
                message=result.message,
                payload=result.payload,
            )
        except Exception as exc:
            logger.exception("MonitorAgent: watcher %s raised an exception", watcher.name)
            return WatcherSummary(
                name=watcher.name,
                healthy=False,
                severity="critical",
                message=f"Watcher raised an exception: {exc}",
                payload={"exception": str(exc)},
            )

    @staticmethod
    def _severity_to_str(severity: Severity) -> str:
        value = getattr(severity, "value", severity)
        s = str(value).strip().lower()
        if s in ("warning", "critical"):
            return s
        return "info"

    def _worst_severity(self, summaries: List[WatcherSummary]) -> str:
        worst = "info"
        for s in summaries:
            if self._SEVERITY_RANK.get(s.severity, 0) > self._SEVERITY_RANK.get(worst, 0):
                worst = s.severity
        return worst

    @staticmethod
    def _build_summary_text(
        overall_healthy: bool,
        overall_severity: str,
        alerts: List[WatcherSummary],
    ) -> str:
        if overall_healthy:
            return "All systems nominal."
        alert_names = ", ".join(a.name for a in alerts)
        count = len(alerts)
        return (
            f"{count} alert(s) — severity={overall_severity} — "
            f"affected watchers: [{alert_names}]"
        )
