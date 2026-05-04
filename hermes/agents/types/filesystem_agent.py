"""
FilesystemAgent — scoped cleanup agent.

Knows which directories are safe to touch (from config/filesystem.yaml),
delegates the actual deletion to AutonomousExecutor, and returns a
structured result dict.

Usage
-----
    from hermes.agents.filesystem_agent import FilesystemAgent

    agent = FilesystemAgent(services_config, filesystem_config)

    # Scan safe paths and return a cleanup plan (no side effects)
    plan = agent.scan()

    # Execute cleanup on a single safe path
    result = agent.cleanup_path("/var/lib/hermes/cache")

    # Execute all items in a plan (auto-rejects non-approved paths)
    results = agent.execute_plan(plan)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from hermes.executor.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PathScanResult:
    path: str
    exists: bool
    size_bytes: int        # 0 when path does not exist
    file_count: int        # 0 when path does not exist
    safe: bool             # True → on the safe_paths allowlist

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CleanupPlan:
    targets: List[PathScanResult]   # only paths where exists=True and safe=True
    total_size_bytes: int
    skipped: List[str]              # paths that exist but were not safe


@dataclass
class CleanupResult:
    path: str
    status: str          # "success" | "failed" | "skipped" | "not_found"
    bytes_freed: int     # best-effort — size captured before deletion
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FilesystemAgent:
    """
    Parameters
    ----------
    services_config:
        Dict loaded from config/services.yaml (passed straight to AutonomousExecutor).
    filesystem_config:
        Dict loaded from config/filesystem.yaml.
        Expected keys: safe_paths (list[str]), restricted_paths (list[str]).
    """

    def __init__(
        self,
        services_config: Dict[str, Any],
        filesystem_config: Dict[str, Any],
    ) -> None:
        self.safe_paths: List[str] = filesystem_config.get("safe_paths", [])
        self.restricted_paths: List[str] = filesystem_config.get("restricted_paths", [])
        self._executor = AutonomousExecutor(services_config)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> CleanupPlan:
        """
        Inspect every safe_path and return a CleanupPlan.
        No files are deleted.
        """
        targets: List[PathScanResult] = []
        skipped: List[str] = []

        for path in self.safe_paths:
            result = self._scan_path(path)
            if result.exists and result.safe:
                targets.append(result)
            elif result.exists and not result.safe:
                skipped.append(path)

        total = sum(t.size_bytes for t in targets)
        return CleanupPlan(targets=targets, total_size_bytes=total, skipped=skipped)

    def cleanup_path(self, path: str) -> CleanupResult:
        """
        Clean up a single path.

        The path must be on the safe_paths allowlist; any attempt to clean
        a restricted or unknown path is rejected before reaching the executor.
        """
        if not self._is_safe(path):
            logger.warning("FilesystemAgent: rejected unsafe path %s", path)
            return CleanupResult(
                path=path,
                status="skipped",
                bytes_freed=0,
                error="Path is not on the safe_paths allowlist.",
            )

        if not os.path.exists(path):
            return CleanupResult(path=path, status="not_found", bytes_freed=0)

        size_before = self._path_size(path)

        try:
            exec_result = self._executor.cleanup_path(path)
            status = exec_result.get("status", "failed")
            error = exec_result.get("error", "")
            bytes_freed = size_before if status == "success" else 0
            logger.info(
                "FilesystemAgent: cleanup_path %s → %s (freed ~%d bytes)",
                path, status, bytes_freed,
            )
            return CleanupResult(
                path=path, status=status, bytes_freed=bytes_freed, error=error or ""
            )
        except Exception as exc:
            logger.exception("FilesystemAgent: executor raised on path %s", path)
            return CleanupResult(
                path=path, status="failed", bytes_freed=0, error=str(exc)
            )

    def execute_plan(self, plan: CleanupPlan) -> List[CleanupResult]:
        """
        Run cleanup on every target in a CleanupPlan.
        Each path is re-validated independently; a failure on one path does
        not prevent the rest from running.
        """
        results: List[CleanupResult] = []
        for target in plan.targets:
            result = self.cleanup_path(target.path)
            results.append(result)
        return results

    def status_summary(self) -> Dict[str, Any]:
        """
        Convenience method: scan and return a plain dict ready for LLM context
        or Planner.plan(system_status=...).
        """
        plan = self.scan()
        return {
            "safe_paths": self.safe_paths,
            "scannable_targets": len(plan.targets),
            "total_reclaimable_bytes": plan.total_size_bytes,
            "skipped_paths": plan.skipped,
            "targets": [t.to_dict() for t in plan.targets],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_safe(self, path: str) -> bool:
        """True only if path starts with a known safe_path entry."""
        return any(path.startswith(sp) for sp in self.safe_paths)

    @staticmethod
    def _path_size(path: str) -> int:
        """Return total size in bytes of all files under path. Never raises."""
        total = 0
        try:
            if os.path.isfile(path):
                return os.path.getsize(path)
            for dirpath, _dirs, files in os.walk(path):
                for fname in files:
                    try:
                        total += os.path.getsize(os.path.join(dirpath, fname))
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    @staticmethod
    def _scan_path(path: str) -> PathScanResult:
        exists = os.path.exists(path)
        if not exists:
            return PathScanResult(
                path=path, exists=False, size_bytes=0, file_count=0, safe=True
            )
        size = FilesystemAgent._path_size(path)
        file_count = sum(len(files) for _, _, files in os.walk(path)) if os.path.isdir(path) else 1
        return PathScanResult(
            path=path, exists=True, size_bytes=size, file_count=file_count, safe=True
        )
