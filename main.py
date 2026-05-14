#!/usr/bin/env python3
"""
main.py
Hermes TUI client launcher.

Notes:
- Cross-platform: Windows + Linux
- Does not modify agents.yaml
- Quitting TUI does not stop daemon
"""

from pathlib import Path
import os
import sys
import time
import signal
import subprocess
import sqlite3
import urllib.request
import urllib.error
import json
import yaml
import concurrent.futures
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box
from hermes.runtime.state import is_daemon_running, get_daemon_pid
from hermes.runtime.spawner import AgentSpawner

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR   = PROJECT_ROOT / "config"
SERVICES_YAML = CONFIG_DIR / "services.yaml"
AGENTS_YAML   = CONFIG_DIR / "agents.yaml"
PLUGINS_YAML  = CONFIG_DIR / "plugins.yaml"
LOG_FILE      = PROJECT_ROOT / "hermes.log"
DB_FILE       = PROJECT_ROOT / "hermes.sqlite3"
HERMESD_FILE  = PROJECT_ROOT / "hermesd.py"


def _api_base_url() -> str | None:
    services_cfg = _load_yaml(SERVICES_YAML)
    daemon_cfg = services_cfg.get("daemon", {}) if isinstance(services_cfg, dict) else {}
    flask_cfg = services_cfg.get("flask", {}) if isinstance(services_cfg, dict) else {}
    merged = dict(flask_cfg)
    merged.update(daemon_cfg.get("api", {}))
    if not merged.get("enabled", True):
        return None
    host = str(merged.get("host", "127.0.0.1"))
    port = int(merged.get("port", 5000))
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _fetch_api_json(path: str, timeout: float = 1.5):
    base = _api_base_url()
    if not base:
        return None
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _pid_uptime_seconds() -> int | None:
    pid = get_daemon_pid()
    if not pid:
        return None
    try:
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            fields = stat.read_text(encoding="utf-8", errors="ignore").split()
            start_ticks = int(fields[21])
            hz = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                uptime = float(f.read().split()[0])
            start_seconds = start_ticks / hz
            return int(max(0, uptime - start_seconds))
    except Exception:
        return None
    return None


def _fallback_recent_events(limit: int = 5) -> list[dict]:
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT created_at, severity, source, message FROM events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _fallback_active_agents() -> list[dict]:
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT agent_id, name, type, status FROM agent_nodes ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _status_snapshot() -> dict:
    running = is_daemon_running()
    pid = get_daemon_pid() if running else None
    uptime = _pid_uptime_seconds() if running else None

    status_api = _fetch_api_json("/api/status") if running else None
    events_api = _fetch_api_json("/api/events?limit=5") if running else None

    services_cfg = _load_yaml(SERVICES_YAML)
    daemon_cfg = services_cfg.get("daemon", {}) if isinstance(services_cfg, dict) else {}
    flask_cfg = services_cfg.get("flask", {}) if isinstance(services_cfg, dict) else {}
    merged_flask = dict(flask_cfg)
    merged_flask.update(daemon_cfg.get("api", {}))

    if status_api:
        alerts = status_api.get("alerts", [])
    else:
        alerts = []

    if events_api is None:
        events = _fallback_recent_events(5)
    else:
        events = events_api

    return {
        "running": running,
        "pid": pid,
        "uptime": uptime,
        "alerts": alerts,
        "events": events,
        "active_agents": _fallback_active_agents(),
        "flask": {
            "enabled": bool(merged_flask.get("enabled", True)),
            "host": str(merged_flask.get("host", "127.0.0.1")),
            "port": int(merged_flask.get("port", 5000)),
        },
    }


def _format_uptime(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d > 0:
        return f"{d}d {h}h {m}m"
    return f"{h}h {m}m {s}s"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _save_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _validate_console_config() -> bool:
    services = _load_yaml(SERVICES_YAML)
    agents = _load_yaml(AGENTS_YAML)
    daemon = services.get("daemon", {}) if isinstance(services, dict) else {}
    flask_top = services.get("flask", {}) if isinstance(services, dict) else {}
    merged_flask = dict(flask_top)
    merged_flask.update(daemon.get("api", {}) if isinstance(daemon, dict) else {})
    planner = (agents.get("system_agents") or {}).get("planner") if isinstance(agents, dict) else None

    if daemon.get("tick_seconds") is None or daemon.get("dedup_repeat_seconds") is None:
        return False
    if merged_flask.get("enabled") not in (True, False):
        return False
    if not isinstance(planner, dict):
        return False
    for key in ("provider", "endpoint", "model"):
        if planner.get(key) in (None, "", "not-set"):
            return False
    return True


def _pause(msg: str = "Press Enter to continue"):
    try:
        Prompt.ask(f"[dim]{msg}[/dim]", default="")
    except (KeyboardInterrupt, EOFError):
        pass


def _ask_nonempty(prompt: str, default: str | None = None) -> str:
    while True:
        value = Prompt.ask(prompt, default=default if default is not None else "").strip()
        if value:
            return value
        if default is not None:
            return default
        console.print("[yellow]Please enter a value.[/yellow]")


def _ask_int(prompt: str, default: int) -> int:
    while True:
        raw = Prompt.ask(prompt, default=str(default)).strip()
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            console.print("[yellow]Please enter a valid integer.[/yellow]")


def _port_in_use(host: str, port: int) -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex((host, port)) == 0
    except OSError:
        return False


def _read_last_lines(path: Path, lines: int = 50) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            data = f.readlines()
        return "".join(data[-lines:])
    except Exception as e:
        return f"[error reading log: {e}]"


# ── First-run wizard ───────────────────────────────────────────────────────────

def run_wizard():
    if is_daemon_running():
        console.print("[yellow]Daemon is already running. Skipping first-run setup.[/yellow]")
        return

    console.print(
        Panel(
            "[bold cyan]Hermes — First Run Setup[/bold cyan]\n"
            "[dim]Missing config detected. This will create safe defaults.[/dim]",
            box=box.DOUBLE_EDGE,
        )
    )

    api_enabled = Confirm.ask("Enable Flask REST API?", default=True)
    host = "127.0.0.1"
    port = 5000
    if api_enabled:
        host_in = Prompt.ask("API host", default="127.0.0.1").strip()
        host = host_in or "127.0.0.1"
        port = _ask_int("API port", 5000)
        while _port_in_use(host, port):
            console.print(f"[yellow]Port {port} is already in use.[/yellow]")
            port = _ask_int("Choose a different port", port + 1)

    tg_enabled = Confirm.ask("Enable Telegram notifications/approvals?", default=False)
    tg_token = ""
    tg_chat_id = ""
    tg_user_ids = []
    if tg_enabled:
        tg_token    = _ask_nonempty("Telegram Bot Token")
        tg_chat_id  = _ask_nonempty("Telegram Chat ID")
        tg_uid      = _ask_int("Telegram User ID", 0)
        if tg_uid != 0:
            tg_user_ids = [tg_uid]

    services_cfg = _load_yaml(SERVICES_YAML)
    services_cfg.setdefault("managed_services", [])
    services_cfg["daemon"] = services_cfg.get("daemon", {})
    services_cfg["daemon"]["tick_seconds"]         = services_cfg["daemon"].get("tick_seconds", 10)
    services_cfg["daemon"]["dedup_repeat_seconds"] = services_cfg["daemon"].get("dedup_repeat_seconds", 300)
    services_cfg["daemon"]["api"] = {
        "enabled": api_enabled,
        "host":    host,
        "port":    port,
    }
    services_cfg["flask"] = {
        "enabled": api_enabled,
        "host":    host,
        "port":    port,
    }
    _save_yaml(SERVICES_YAML, services_cfg)

    plugins_cfg = _load_yaml(PLUGINS_YAML)
    plugins_cfg.setdefault("active", {})
    plugins_cfg["active"].setdefault("communication", {})
    plugins_cfg["active"]["communication"]["telegram"] = {
        "input":                tg_enabled,
        "output":               tg_enabled,
        "system_notifications": tg_enabled,
    }
    plugins_cfg.setdefault("plugins", {})
    if tg_enabled:
        plugins_cfg["plugins"]["telegram"] = {
            "token":            tg_token,
            "chat_id":          tg_chat_id,
            "allowed_user_ids": tg_user_ids,
            "approvals":        {"enabled": True},
        }
    _save_yaml(PLUGINS_YAML, plugins_cfg)

    if not AGENTS_YAML.exists():
        _save_yaml(
            AGENTS_YAML,
            {
                "system_agents": {
                    "planner": {"model": "not-set", "provider": "not-set", "endpoint": "not-set"},
                    "router":  {"model": "not-set", "provider": "not-set", "endpoint": "not-set"},
                },
                "custom_agents": {"agents": []},
            },
        )

    console.print("[green]Config written.[/green]")


# ── Daemon control ─────────────────────────────────────────────────────────────

def start_daemon():
    if not HERMESD_FILE.exists():
        console.print(f"[red]Missing file: {HERMESD_FILE}[/red]")
        return

    if is_daemon_running():
        console.print(f"[yellow]Daemon already running.[/yellow] [dim](PID {get_daemon_pid()})[/dim]")
        return

    console.print("[dim]Starting daemon...[/dim]")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = LOG_FILE.open("a", encoding="utf-8")

    kwargs = {
        "args":   [sys.executable, str(HERMESD_FILE)],
        "stdout": log_handle,
        "stderr": log_handle,
        "stdin":  subprocess.DEVNULL,
        "cwd":    str(PROJECT_ROOT),
    }

    if os.name == "nt":
        creationflags = 0
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            creationflags |= subprocess.DETACHED_PROCESS
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    try:
        subprocess.Popen(**kwargs)
    except Exception as e:
        console.print(f"[red]Failed to launch daemon:[/red] {e}")
        return

    for _ in range(30):
        time.sleep(0.5)
        if is_daemon_running():
            pid = get_daemon_pid()
            flask_cfg = _status_snapshot().get("flask", {})
            if flask_cfg.get("enabled", True):
                if _fetch_api_json("/api/status", timeout=0.8) is not None:
                    console.print(f"[green]Daemon started.[/green] [dim](PID {pid})[/dim]")
                    return
                console.print(f"[green]Daemon started.[/green] [dim](PID {pid}, API warming up)[/dim]")
                return
            console.print(f"[green]Daemon started.[/green] [dim](PID {pid})[/dim]")
            return

    console.print("[red]Daemon did not start within 15 seconds.[/red]")
    if LOG_FILE.exists():
        tail = _read_last_lines(LOG_FILE, 20).strip()
        if tail:
            console.print("\n[bold]Last log lines:[/bold]")
            console.print(tail)
    console.print("[dim]Check hermes.log for the underlying error.[/dim]")


def stop_daemon():
    pid = get_daemon_pid()
    if not pid:
        console.print("[yellow]Daemon is not running.[/yellow]")
        return

    if not Confirm.ask(f"Stop daemon (PID {pid})?", default=False):
        console.print("[dim]Cancelled.[/dim]")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        console.print("[green]Stop signal sent.[/green]")
    except ProcessLookupError:
        console.print("[yellow]Process not found; it may already be stopped.[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to stop daemon:[/red] {e}")


def reload_config():
    pid = get_daemon_pid()
    if not pid:
        console.print("[yellow]Daemon is not running.[/yellow]")
        return

    if os.name == "nt" or not hasattr(signal, "SIGHUP"):
        console.print("[yellow]Config reload via SIGHUP is not supported on Windows yet.[/yellow]")
        return

    try:
        os.kill(pid, signal.SIGHUP)
        console.print("[green]SIGHUP sent. Daemon should reload config.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to reload config:[/red] {e}")


# ── Pending approvals ──────────────────────────────────────────────────────────

def _get_pending_tasks() -> list:
    try:
        from hermes.services import task_service
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(task_service.list_pending, 10)
            return future.result(timeout=2.0)
    except Exception:
        return []


def _render_pending_panel(pending: list):
    """Render the pending approvals panel on the home screen."""
    if not pending:
        return

    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold yellow",
        padding=(0, 1),
        expand=True,
    )
    table.add_column("ID",       style="bold", width=6)
    table.add_column("Type",     style="cyan")
    table.add_column("Title",    style="white")
    table.add_column("Priority", justify="right", width=8)
    table.add_column("Created",  style="dim", width=20)

    for t in pending:
        table.add_row(
            str(t["id"]),
            t.get("type", "?"),
            t.get("title", ""),
            str(t.get("priority", "")),
            str(t.get("created_at", ""))[:19],
        )

    console.print(
        Panel(
            table,
            title=f"[bold yellow]⚠  Pending Approvals ({len(pending)})[/bold yellow]",
            border_style="yellow",
            box=box.ROUNDED,
        )
    )


def review_pending_tasks():
    """Interactive approve/deny loop for blocked tasks."""
    pending = _get_pending_tasks()

    if not pending:
        console.print("[green]No tasks pending approval.[/green]")
        _pause()
        return

    try:
        from hermes.services import task_service
    except Exception as e:
        console.print(f"[red]Could not load task_service:[/red] {e}")
        _pause()
        return

    while True:
        console.clear()
        console.print(
            Panel(
                "[bold yellow]Pending Approvals[/bold yellow]\n"
                "[dim]Review and approve or deny each blocked task.[/dim]",
                box=box.DOUBLE_EDGE,
            )
        )

        pending = _get_pending_tasks()
        if not pending:
            console.print("[green]All tasks resolved.[/green]")
            _pause()
            return

        # Render task list
        table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold yellow", expand=True)
        table.add_column("#",        style="bold dim", width=4)
        table.add_column("ID",       style="bold",     width=6)
        table.add_column("Type",     style="cyan")
        table.add_column("Title",    style="white")
        table.add_column("Priority", justify="right",  width=8)
        table.add_column("Created",  style="dim",      width=20)

        for i, t in enumerate(pending, 1):
            table.add_row(
                str(i),
                str(t["id"]),
                t.get("type", "?"),
                t.get("title", ""),
                str(t.get("priority", "")),
                str(t.get("created_at", ""))[:19],
            )

        console.print(table)
        console.print()
        console.print("[dim]Enter task # to review, or [bold]q[/bold] to go back.[/dim]")

        try:
            raw = Prompt.ask("[bold]>[/bold]", default="").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return

        if raw in {"q", "quit", "back", ""}:
            return

        try:
            idx = int(raw)
            if not (1 <= idx <= len(pending)):
                raise ValueError
        except ValueError:
            console.print("[yellow]Invalid selection.[/yellow]")
            time.sleep(0.8)
            continue

        task = pending[idx - 1]
        _review_single_task(task, task_service)


def _review_single_task(task: dict, task_service):
    """Show full task detail and prompt approve / deny."""
    console.clear()
    console.print(
        Panel(
            f"[bold]Task #{task['id']}[/bold]  [cyan]{task.get('type', '?')}[/cyan]",
            box=box.ROUNDED,
            border_style="yellow",
        )
    )

    # Detail table
    detail = Table(box=None, show_header=False, padding=(0, 1))
    detail.add_column("k", style="bold dim", width=14)
    detail.add_column("v")
    detail.add_row("ID",       str(task["id"]))
    detail.add_row("Type",     task.get("type", "?"))
    detail.add_row("Title",    task.get("title", ""))
    detail.add_row("Priority", str(task.get("priority", "")))
    detail.add_row("Created",  str(task.get("created_at", ""))[:19])

    # Show payload if present (full detail fetch)
    full = task_service.get_task(task["id"]) or task
    payload = full.get("payload") or {}
    if payload:
        import json
        detail.add_row("Payload", json.dumps(payload, indent=2))

    console.print(detail)
    console.print()
    console.print(" [bold green]a[/bold green]  Approve")
    console.print(" [bold red]d[/bold red]  Deny")
    console.print(" [bold dim]b[/bold dim]  Back")
    console.print()

    while True:
        try:
            action = Prompt.ask("[bold]>[/bold]", default="").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return

        if action in {"a", "approve"}:
            result = task_service.approve_task(task["id"])
            if result.get("ok"):
                console.print(f"[green]Task #{task['id']} approved and queued.[/green]")
            else:
                console.print(f"[red]Failed:[/red] {result.get('error', 'unknown error')}")
            _pause()
            return

        elif action in {"d", "deny"}:
            try:
                reason = Prompt.ask("[dim]Reason (optional)[/dim]", default="").strip() or None
            except (KeyboardInterrupt, EOFError):
                reason = None
            result = task_service.deny_task(task["id"], reason=reason)
            if result.get("ok"):
                console.print(f"[red]Task #{task['id']} denied.[/red]")
            else:
                console.print(f"[red]Failed:[/red] {result.get('error', 'unknown error')}")
            _pause()
            return

        elif action in {"b", "back", ""}:
            return

        else:
            console.print("[yellow]Enter a, d, or b.[/yellow]")


# ── Status bar ─────────────────────────────────────────────────────────────────

def render_status_bar():
    snap = _status_snapshot()
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("k", style="bold dim", width=14)
    table.add_column("v")

    if snap["running"]:
        table.add_row("Daemon", f"[green]Running[/green] [dim](PID {snap['pid']})[/dim]")
        table.add_row("Uptime", _format_uptime(snap["uptime"]))
    else:
        table.add_row("Daemon", "[red]Stopped[/red]")

    flask = snap["flask"]
    if flask["enabled"]:
        table.add_row("Flask", f"[cyan]http://{flask['host']}:{flask['port']}[/cyan]")
    else:
        table.add_row("Flask", "[dim]Disabled[/dim]")

    table.add_row("Active Agents", str(len(snap.get("active_agents", []))))
    table.add_row("Recent Alerts", str(len(snap.get("alerts", []))))

    console.print(table)

    events = snap.get("events", [])[:5]
    if events:
        ev_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        ev_table.add_column("When", style="dim", width=20)
        ev_table.add_column("Severity", width=10)
        ev_table.add_column("Source", width=14)
        ev_table.add_column("Message")
        for e in events:
            ev_table.add_row(
                str(e.get("created_at", ""))[:19],
                str(e.get("severity", "")).upper(),
                str(e.get("source", "")),
                str(e.get("message", "")),
            )
        console.print(Panel(ev_table, title="Recent Events", box=box.ROUNDED))

    active_agents = snap.get("active_agents", [])[:8]
    if active_agents:
        ag_table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold")
        ag_table.add_column("Agent ID", style="dim")
        ag_table.add_column("Name")
        ag_table.add_column("Type", style="cyan")
        ag_table.add_column("Status")
        for a in active_agents:
            ag_table.add_row(
                str(a.get("agent_id", "")),
                str(a.get("name", "")),
                str(a.get("type", "")),
                str(a.get("status", "")),
            )
        console.print(Panel(ag_table, title="Active Agents", box=box.ROUNDED))


# ── Logs ───────────────────────────────────────────────────────────────────────

def view_logs(lines: int = 50):
    console.print(Panel(f"[bold]Live logs — {LOG_FILE.name}[/bold]  [dim](Ctrl+C to return)[/dim]", box=box.SIMPLE))
    if not LOG_FILE.exists():
        console.print("[dim]No log file found yet.[/dim]")
        _pause()
        return

    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
        for line in f.readlines()[-lines:]:
            console.print(line.rstrip())
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.2)
                    continue
                console.print(line.rstrip())
        except KeyboardInterrupt:
            return


# ── Chat ───────────────────────────────────────────────────────────────────────

def create_new_agent_wizard():
    cfg = _load_yaml(AGENTS_YAML)
    custom = cfg.setdefault("custom_agents", {})
    agents = custom.setdefault("agents", [])

    name = _ask_nonempty("Agent name")
    agent_type = Prompt.ask("Agent type", default="chat").strip() or "chat"
    provider = Prompt.ask("Provider", default="ollama").strip() or "ollama"
    endpoint = Prompt.ask("Endpoint", default="http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
    model = _ask_nonempty("Model", default="llama3.1")
    timeout_seconds = _ask_int("Timeout seconds", 20)
    system_prompt = Prompt.ask("System prompt", default="You are Hermes.")

    existing = {str(a.get("name", "")).strip().lower() for a in agents}
    final_name = name
    if name.strip().lower() in existing:
        suffix = 2
        while f"{name} {suffix}".strip().lower() in existing:
            suffix += 1
        final_name = f"{name} {suffix}"

    agents.append(
        {
            "name": final_name,
            "type": agent_type,
            "provider": provider,
            "endpoint": endpoint,
            "model": model,
            "timeout_seconds": timeout_seconds,
            "temperature": 0,
            "system_prompt": system_prompt,
            "enabled": True,
        }
    )
    _save_yaml(AGENTS_YAML, cfg)
    if final_name != name:
        console.print(f"[yellow]Agent name '{name}' already existed. Saved as '{final_name}'.[/yellow]")
    console.print(f"[green]Agent '{final_name}' created.[/green]")
    _pause()


def pick_any_agent() -> dict | None:
    spawner = AgentSpawner()
    system_agents = spawner.get_system_agents()
    custom_agents = spawner.get_custom_agents()

    entries = []
    for agent in system_agents:
        entries.append({"agent": agent, "source": "system"})
    for agent in custom_agents:
        entries.append({"agent": agent, "source": "custom"})

    if not entries:
        console.print("[yellow]No agents available.[/yellow]")
        _pause()
        return None

    console.print("\n[bold]Available agents:[/bold]")
    for i, entry in enumerate(entries, 1):
        agent = entry["agent"]
        agent_id = (agent.config.agent_id or "")[:8]
        label = f"{agent.config.name} [dim]({agent.config.type}, {entry['source']}, id={agent_id})[/dim]"
        console.print(f"  [bold]{i}[/bold] {label}")
    console.print("  [bold]0[/bold] Cancel")

    raw = Prompt.ask("Select agent", default="0").strip()
    try:
        idx = int(raw)
        if idx == 0:
            return None
        if 1 <= idx <= len(entries):
            return entries[idx - 1]
    except ValueError:
        pass

    console.print("[yellow]Invalid selection.[/yellow]")
    return None


def chat_loop(agent_entry: dict):
    from hermes.chat.terminal import HermesTerminal
    agent = agent_entry.get("agent") if isinstance(agent_entry, dict) else None

    if not agent:
        console.print("[red]Selected agent is unavailable.[/red]")
        _pause()
        return

    HermesTerminal(agent).run()


# ── Home screen ────────────────────────────────────────────────────────────────

def show_home(pending: list):
    console.clear()
    console.print(
        Panel(
            "[bold cyan]Hermes Operator Console[/bold cyan] [dim]EVO-T1[/dim]",
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
    )
    render_status_bar()
    console.print()

    if pending:
        _render_pending_panel(pending)
        console.print()

    console.print(" [bold cyan]1[/bold cyan] Start Daemon")
    console.print(" [bold cyan]2[/bold cyan] Stop Daemon")
    console.print(" [bold cyan]3[/bold cyan] Restart Daemon")
    console.print(" [bold cyan]4[/bold cyan] Attach Chat to Agent")
    console.print(" [bold cyan]5[/bold cyan] Create New Agent")
    console.print(" [bold cyan]6[/bold cyan] Live Log Viewer")
    console.print(" [bold cyan]7[/bold cyan] Reload Config")

    if pending:
        console.print(f" [bold yellow]8[/bold yellow] Review Approvals [yellow]({len(pending)} pending)[/yellow]")
    else:
        console.print(" [bold dim]8[/bold dim] [dim]Review Approvals[/dim]")

    console.print()
    console.print(" [bold cyan]q[/bold cyan] Detach Console [dim](daemon keeps running)[/dim]")
    console.print()


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    if not is_daemon_running() and not _validate_console_config():
        run_wizard()
        _pause()

    while True:
        pending = _get_pending_tasks()
        show_home(pending)

        try:
            choice = Prompt.ask("[bold]>[/bold]", default="").strip().lower()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Detaching terminal. Daemon keeps running.[/dim]")
            return

        if choice == "":
            continue
        elif choice == "1":
            start_daemon()
            _pause()
        elif choice == "2":
            stop_daemon()
            _pause()
        elif choice == "3":
            if is_daemon_running():
                stop_daemon()
                time.sleep(1)
            start_daemon()
            _pause()
        elif choice == "4":
            selected = pick_any_agent()
            if selected:
                chat_loop(selected)
        elif choice == "5":
            create_new_agent_wizard()
        elif choice == "6":
            view_logs()
        elif choice == "7":
            reload_config()
            _pause()
        elif choice == "8":
            review_pending_tasks()
        elif choice in {"q", "quit", "exit"}:
            console.print("[dim]Detaching terminal. Daemon keeps running.[/dim]")
            return
        else:
            console.print("[yellow]Unknown option.[/yellow]")
            time.sleep(0.5)


if __name__ == "__main__":
    main()