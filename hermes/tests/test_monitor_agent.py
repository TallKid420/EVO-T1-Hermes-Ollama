"""
Tests for MonitorAgent.
All watcher calls are mocked — no real system checks.
"""
import pytest
from unittest.mock import MagicMock, patch
from hermes.agents.monitor_agent import MonitorAgent, SystemStatus, WatcherSummary
from hermes.watchers.base import WatcherResult
from hermes.core.severity import Severity


def _make_result(triggered: bool, severity: Severity, message: str, source: str = "test") -> WatcherResult:
    return WatcherResult(
        triggered=triggered,
        severity=severity,
        event_type="test",
        source=source,
        message=message,
        payload={},
    )


def _make_watcher(name: str, result: WatcherResult) -> MagicMock:
    w = MagicMock()
    w.name = name
    w.check.return_value = result
    return w


# --- all healthy ---

def test_all_healthy_returns_nominal():
    watchers = [
        _make_watcher("disk", _make_result(False, Severity.INFO, "Disk OK")),
        _make_watcher("memory", _make_result(False, Severity.INFO, "Memory OK")),
    ]
    agent = MonitorAgent(watchers)
    status = agent.get_status()

    assert status.overall_healthy is True
    assert status.overall_severity == "info"
    assert status.alerts == []
    assert status.summary_text == "All systems nominal."


# --- one alert ---

def test_one_alert_surfaces_correctly():
    watchers = [
        _make_watcher("disk", _make_result(True, Severity.WARNING, "Disk at 85%")),
        _make_watcher("memory", _make_result(False, Severity.INFO, "Memory OK")),
    ]
    agent = MonitorAgent(watchers)
    status = agent.get_status()

    assert status.overall_healthy is False
    assert status.overall_severity == "warning"
    assert len(status.alerts) == 1
    assert status.alerts[0].name == "disk"
    assert "disk" in status.summary_text


# --- critical beats warning ---

def test_worst_severity_is_critical():
    watchers = [
        _make_watcher("disk", _make_result(True, Severity.WARNING, "Disk at 85%")),
        _make_watcher("memory", _make_result(True, Severity.CRITICAL, "OOM")),
    ]
    agent = MonitorAgent(watchers)
    status = agent.get_status()

    assert status.overall_severity == "critical"
    assert len(status.alerts) == 2


# --- crashing watcher becomes CRITICAL alert, doesn't propagate ---

def test_crashing_watcher_becomes_critical_alert():
    bad = MagicMock()
    bad.name = "bad_watcher"
    bad.check.side_effect = RuntimeError("exploded")

    good = _make_watcher("memory", _make_result(False, Severity.INFO, "OK"))

    agent = MonitorAgent([bad, good])
    status = agent.get_status()

    assert status.overall_healthy is False
    assert status.overall_severity == "critical"
    assert any(a.name == "bad_watcher" for a in status.alerts)


# --- to_dict is serialisable ---

def test_to_dict_is_json_serialisable():
    import json
    watchers = [_make_watcher("disk", _make_result(False, Severity.INFO, "OK"))]
    agent = MonitorAgent(watchers)
    status = agent.get_status()
    # should not raise
    json.dumps(status.to_dict())


# --- from_config smoke test (mocked file I/O) ---

def test_from_config_builds_agent(tmp_path):
    services_yaml = tmp_path / "services.yaml"
    services_yaml.write_text("managed_services: []\n")

    with patch("hermes.agents.monitor_agent.OllamaHealthWatcher"), \
         patch("hermes.agents.monitor_agent.DiskPressureWatcher"), \
         patch("hermes.agents.monitor_agent.MemoryPressureWatcher"), \
         patch("hermes.agents.monitor_agent.ServiceStatusWatcher"):
        agent = MonitorAgent.from_config(services_config_path=str(services_yaml))
        assert isinstance(agent, MonitorAgent)
        assert len(agent.watchers) == 4