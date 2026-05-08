"""
hermes/agents/system/server_agent.py

ServerAgent — LLM-powered operator agent built on LangChain tool-calling.

- Spawned via AgentFactory using the "server" preset from agents.yaml
- Uses LangChain's bind_tools() + tool-calling loop (ReAct style)
- Has access to real system tools: disk, memory, cpu, logs, services, restart
- Proactively monitors via monitor_tick() and queues tasks through approval flow
- Direct chat interface: you talk to it from the TUI
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
import yaml

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langchain_core.tools import tool

from hermes.agents.base_agent import BaseAgent
from hermes.agents.types.monitor_agent import MonitorAgent
from hermes.config_loader import AgentConfig
from hermes.plugins.provider.llm_provider import LLMProvider
from hermes.services import task_service, event_service

logger = logging.getLogger(__name__)

_SERVICES_YAML = Path("config/services.yaml")
_LOG_FILE = Path("hermes.log")
_AUTO_TASK_SEVERITY = {"critical"}

# ── LangChain Tools ────────────────────────────────────────────────────────────

@tool
def get_system_snapshot() -> Dict[str, Any]:
    """Get a full system snapshot: CPU percent, load averages, memory usage, and disk usage."""
    mem  = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load = psutil.getloadavg()
    cpu  = psutil.cpu_percent(interval=0.5)
    return {
        "cpu_percent": cpu,
        "load_avg": {"1m": load[0], "5m": load[1], "15m": load[2]},
        "memory": {
            "total_gb":     round(mem.total     / 1e9, 1),
            "used_gb":      round(mem.used      / 1e9, 1),
            "available_gb": round(mem.available / 1e9, 1),
            "percent":      mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1e9, 1),
            "used_gb":  round(disk.used  / 1e9, 1),
            "free_gb":  round(disk.free  / 1e9, 1),
            "percent":  disk.percent,
        },
    }


@tool
def get_top_processes(n: int = 8) -> List[Dict[str, Any]]:
    """Get the top N processes sorted by CPU usage."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(procs, key=lambda x: x.get("cpu_percent") or 0, reverse=True)[:n]


@tool
def get_disk_largest_dirs(path: str = "/", top_n: int = 5) -> List[Dict[str, Any]]:
    """Find the largest top-level directories under a given path."""
    results = []
    try:
        root = Path(path)
        for child in sorted(root.iterdir()):
            if child.is_symlink():
                continue
            try:
                usage = shutil.disk_usage(str(child))
                results.append({"path": str(child), "used_gb": round(usage.used / 1e9, 2)})
            except (PermissionError, OSError):
                pass
        results.sort(key=lambda x: x["used_gb"], reverse=True)
        return results[:top_n]
    except Exception as e:
        return [{"error": str(e)}]


@tool
def read_log_tail(lines: int = 50, level_filter: Optional[str] = None) -> str:
    """Read the last N lines of hermes.log. Optionally filter by log level (ERROR, WARNING, INFO)."""
    if not _LOG_FILE.exists():
        return "(no log file found)"
    try:
        with _LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines:]
        if level_filter:
            tail = [l for l in tail if level_filter.upper() in l.upper()]
        return "".join(tail).strip() or "(no matching log lines)"
    except Exception as e:
        return f"(error reading log: {e})"


@tool
def get_managed_services() -> List[str]:
    """Return the list of managed services from services.yaml."""
    try:
        with _SERVICES_YAML.open("r") as f:
            cfg = yaml.safe_load(f) or {}
        return [s.get("name", "") for s in cfg.get("managed_services", []) if s.get("name")]
    except Exception as e:
        return [f"error: {e}"]


@tool
def check_service_status(service: str) -> Dict[str, Any]:
    """Check the systemd status of a named service."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=5
        )
        active = result.stdout.strip() == "active"
        return {"service": service, "active": active, "state": result.stdout.strip()}
    except Exception as e:
        return {"service": service, "active": False, "state": f"error: {e}"}


@tool
def get_watcher_status() -> Dict[str, Any]:
    """Run all Hermes watchers and return the full system health status."""
    monitor = MonitorAgent.from_config()
    status  = monitor.get_status()
    return {
        "overall_healthy":  status.overall_healthy,
        "overall_severity": status.overall_severity,
        "summary":          status.summary_text,
        "watchers": [
            {
                "name":     w.name,
                "healthy":  w.healthy,
                "severity": w.severity,
                "message":  w.message,
            }
            for w in status.watchers
        ],
        "alerts": [
            {
                "name":     a.name,
                "severity": a.severity,
                "message":  a.message,
            }
            for a in status.alerts
        ],
    }


@tool
def queue_restart_service(service: str, reason: str = "") -> Dict[str, Any]:
    """
    Queue a service restart task through the Hermes approval system.
    Does NOT restart immediately — goes to approval if risk is high.
    Returns the queued task details.
    """
    managed = get_managed_services.invoke({"service": service}) if False else _get_managed_services_raw()
    if service not in managed:
        return {
            "queued": False,
            "reason": f"'{service}' is not in managed services. Add it to config/services.yaml first.",
            "managed": managed,
        }
    result = task_service.queue_task(
        type_="restart_service",
        payload={"service": service, "reason": reason or "operator request"},
        priority=7,
        risk_score=4,
    )
    return {"queued": True, **result}


@tool
def queue_cleanup_task(target: str = "/tmp", reason: str = "disk pressure") -> Dict[str, Any]:
    """
    Queue a file cleanup task through the Hermes approval system.
    Always requires approval before execution.
    """
    result = task_service.queue_task(
        type_="delete_files",
        payload={"target": target, "reason": reason},
        priority=6,
        risk_score=5,
    )
    return {"queued": True, **result}


def _get_managed_services_raw() -> List[str]:
    """Internal helper — returns managed service names without going through tool wrapper."""
    try:
        with _SERVICES_YAML.open("r") as f:
            cfg = yaml.safe_load(f) or {}
        return [s.get("name", "") for s in cfg.get("managed_services", []) if s.get("name")]
    except Exception:
        return []


# ── Tool registry ──────────────────────────────────────────────────────────────

SERVER_AGENT_TOOLS = [
    get_system_snapshot,
    get_top_processes,
    get_disk_largest_dirs,
    read_log_tail,
    get_managed_services,
    check_service_status,
    get_watcher_status,
    queue_restart_service,
    queue_cleanup_task,
]

_TOOL_MAP = {t.name: t for t in SERVER_AGENT_TOOLS}

# ── System prompt ──────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """
You are the Hermes Server Agent — the always-on operator for a GMKtec EVO-T1 Ubuntu server (64GB RAM, 3TB SSD).

Your job:
- Answer questions about system health, disk, memory, CPU, logs, and services
- Proactively detect and report problems
- Queue fix tasks through the approval system (never execute directly)
- Be concise and direct — the operator is technical

Rules:
- Always use your tools to get real data before answering
- Never guess at system state — call the tool
- For any destructive action (restart, cleanup), use the queue tools — never act directly
- If something is critical, say so clearly
- Keep responses short and factual unless asked for detail
""".strip()


# ── ServerAgent class ──────────────────────────────────────────────────────────

class ServerAgent(BaseAgent):
    """
    LLM-powered Server Agent.

    Built on LangChain tool-calling loop:
      1. User message → LLM with bound tools
      2. LLM calls tools → results fed back
      3. LLM produces final answer

    Spawned via AgentFactory using type="server".
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._llm_raw  = LLMProvider(config)
        self._llm      = self._llm_raw.bind_tools(SERVER_AGENT_TOOLS)
        self._monitor  = MonitorAgent.from_config()
        self._history: List[Any] = []   # rolling conversation history
        logger.info("ServerAgent initialised with model=%s", config.model)

    # ── BaseAgent interface ────────────────────────────────────────────────────

    def run(self, input: Optional[str] = None) -> str:
        """Single-shot run — used by factory/scheduler."""
        if input:
            return self.chat(input)
        return self.chat("Give me a full system status report.")

    def run_loop(self):
        """Autonomous loop — called by daemon for proactive monitoring."""
        import time
        while self.running:
            self.monitor_tick()
            time.sleep(60)

    # ── Chat interface ─────────────────────────────────────────────────────────

    def chat(self, message: str) -> str:
        """
        Handle a direct message from the operator.
        Runs the full LangChain tool-calling loop and returns the final response.
        """
        messages = [SystemMessage(content=_SYSTEM_PROMPT)] + self._history + [HumanMessage(content=message)]

        try:
            response = self._run_tool_loop(messages)
        except Exception as e:
            logger.exception("ServerAgent.chat error")
            return f"[Server Agent error: {e}]"

        # Append to rolling history (keep last 10 turns)
        self._history.append(HumanMessage(content=message))
        self._history.append(AIMessage(content=response))
        if len(self._history) > 20:
            self._history = self._history[-20:]

        return response

    # ── Monitor tick ───────────────────────────────────────────────────────────

    def monitor_tick(self) -> List[Dict[str, Any]]:
        """
        Run all watchers. For any critical alert, queue a task automatically.
        Called by the daemon loop every N seconds.
        """
        queued = []
        try:
            status = self._monitor.get_status()
            for alert in status.alerts:
                if alert.severity not in _AUTO_TASK_SEVERITY:
                    continue

                existing = (
                    task_service.list_tasks(limit=10, status="blocked") +
                    task_service.list_tasks(limit=10, status="queued")
                )
                already_queued = any(
                    t.get("type") == f"server_alert_{alert.name}" for t in existing
                )
                if already_queued:
                    continue

                result = task_service.queue_task(
                    type_=f"server_alert_{alert.name}",
                    payload={
                        "watcher":  alert.name,
                        "severity": alert.severity,
                        "message":  alert.message,
                    },
                    priority=8,
                    risk_score=6,
                )
                queued.append(result)
                logger.warning(
                    "ServerAgent queued task for alert: %s — %s",
                    alert.name, alert.message
                )

                event_service.add_event(
                    severity=alert.severity,
                    source="server_agent",
                    type_=f"server_alert_{alert.name}",
                    message=alert.message,
                    payload={"watcher": alert.name},
                )

        except Exception:
            logger.exception("ServerAgent.monitor_tick error")

        return queued

    # ── Tool-calling loop ──────────────────────────────────────────────────────

    def _run_tool_loop(self, messages: List[Any], max_iterations: int = 6) -> str:
        """
        LangChain tool-calling loop:
          - Send messages to LLM
          - If LLM calls tools, execute them and feed results back
          - Repeat until LLM produces a final text response (no tool calls)
          - Hard cap at max_iterations to prevent runaway loops
        """
        for iteration in range(max_iterations):
            ai_msg = self._llm.invoke(messages)
            messages.append(ai_msg)

            # No tool calls → LLM is done, return the text
            if not getattr(ai_msg, "tool_calls", None):
                return ai_msg.content or "(no response)"

            # Execute each tool call
            for tc in ai_msg.tool_calls:
                tool_name = tc["name"]
                tool_args = tc.get("args", {})
                tool_id   = tc.get("id", tool_name)

                logger.debug("ServerAgent tool call: %s(%s)", tool_name, tool_args)

                tool_fn = _TOOL_MAP.get(tool_name)
                if tool_fn is None:
                    result = f"[error: unknown tool '{tool_name}']"
                else:
                    try:
                        result = tool_fn.invoke(tool_args)
                    except Exception as e:
                        result = f"[tool error: {e}]"

                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tool_id)
                )

        # Hit iteration cap — return whatever the last AI message said
        last = messages[-1]
        if hasattr(last, "content") and last.content:
            return last.content
        return "[Server Agent hit max tool iterations — check logs]"