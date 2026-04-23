"""
Tests for FilesystemAgent.
No real filesystem deletions — executor is mocked.
"""
import os
import pytest
from unittest.mock import MagicMock, patch
from hermes.agents.filesystem_agent import FilesystemAgent, CleanupResult, CleanupPlan


SERVICES_CFG = {"managed_services": []}
FS_CFG = {
    "safe_paths": ["/tmp/hermes_test_cache"],
    "restricted_paths": ["/etc", "/usr"],
}


def _make_agent(executor_result: dict = None) -> FilesystemAgent:
    agent = FilesystemAgent(SERVICES_CFG, FS_CFG)
    agent._executor = MagicMock()
    agent._executor.cleanup_path.return_value = executor_result or {"status": "success", "error": ""}
    return agent


# --- safe path check ---

def test_is_safe_allows_listed_path():
    agent = _make_agent()
    assert agent._is_safe("/tmp/hermes_test_cache") is True
    assert agent._is_safe("/tmp/hermes_test_cache/subdir") is True


def test_is_safe_rejects_unlisted_path():
    agent = _make_agent()
    assert agent._is_safe("/etc/passwd") is False
    assert agent._is_safe("/home/user/documents") is False


# --- cleanup_path rejects unsafe paths before executor ---

def test_cleanup_path_rejects_unsafe():
    agent = _make_agent()
    result = agent.cleanup_path("/etc/passwd")

    assert result.status == "skipped"
    assert result.bytes_freed == 0
    agent._executor.cleanup_path.assert_not_called()


# --- cleanup_path returns not_found for missing path ---

def test_cleanup_path_not_found(tmp_path):
    cfg = {"safe_paths": [str(tmp_path)], "restricted_paths": []}
    agent = FilesystemAgent(SERVICES_CFG, cfg)
    agent._executor = MagicMock()

    result = agent.cleanup_path(str(tmp_path / "nonexistent"))
    assert result.status == "not_found"
    agent._executor.cleanup_path.assert_not_called()


# --- cleanup_path success ---

def test_cleanup_path_success(tmp_path):
    target = tmp_path / "cache"
    target.mkdir()
    (target / "file.txt").write_text("hello")

    cfg = {"safe_paths": [str(tmp_path)], "restricted_paths": []}
    agent = FilesystemAgent(SERVICES_CFG, cfg)
    agent._executor = MagicMock()
    agent._executor.cleanup_path.return_value = {"status": "success", "error": ""}

    result = agent.cleanup_path(str(target))
    assert result.status == "success"
    assert result.bytes_freed > 0


# --- cleanup_path executor failure is isolated ---

def test_cleanup_path_executor_failure(tmp_path):
    target = tmp_path / "cache"
    target.mkdir()

    cfg = {"safe_paths": [str(tmp_path)], "restricted_paths": []}
    agent = FilesystemAgent(SERVICES_CFG, cfg)
    agent._executor = MagicMock()
    agent._executor.cleanup_path.side_effect = RuntimeError("disk error")

    result = agent.cleanup_path(str(target))
    assert result.status == "failed"
    assert "disk error" in result.error


# --- scan returns only existing safe paths ---

def test_scan_only_returns_existing_paths(tmp_path):
    existing = tmp_path / "cache"
    existing.mkdir()
    (existing / "f.txt").write_text("data")

    cfg = {
        "safe_paths": [str(existing), str(tmp_path / "nonexistent")],
        "restricted_paths": [],
    }
    agent = FilesystemAgent(SERVICES_CFG, cfg)
    agent._executor = MagicMock()

    plan = agent.scan()
    assert len(plan.targets) == 1
    assert plan.targets[0].path == str(existing)
    assert plan.total_size_bytes > 0


# --- execute_plan runs all targets ---

def test_execute_plan_runs_all(tmp_path):
    p1 = tmp_path / "a"
    p2 = tmp_path / "b"
    p1.mkdir(); p2.mkdir()

    cfg = {"safe_paths": [str(tmp_path)], "restricted_paths": []}
    agent = FilesystemAgent(SERVICES_CFG, cfg)
    agent._executor = MagicMock()
    agent._executor.cleanup_path.return_value = {"status": "success", "error": ""}

    plan = agent.scan()
    results = agent.execute_plan(plan)
    assert len(results) == len(plan.targets)
    assert all(r.status == "success" for r in results)