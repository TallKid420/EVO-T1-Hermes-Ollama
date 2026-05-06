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
import yaml

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from hermes.runtime.state import is_daemon_running, get_daemon_pid

console = Console()

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
SERVICES_YAML = CONFIG_DIR / "services.yaml"
AGENTS_YAML = CONFIG_DIR / "agents.yaml"
PLUGINS_YAML = CONFIG_DIR / "plugins.yaml"
LOG_FILE = PROJECT_ROOT / "hermes.log"
HERMESD_FILE = PROJECT_ROOT / "hermesd.py"


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


def configs_exist() -> bool:
    return SERVICES_YAML.exists() and AGENTS_YAML.exists() and PLUGINS_YAML.exists()


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


def run_wizard():
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
        tg_token = _ask_nonempty("Telegram Bot Token")
        tg_chat_id = _ask_nonempty("Telegram Chat ID")
        tg_uid = _ask_int("Telegram User ID", 0)
        if tg_uid != 0:
            tg_user_ids = [tg_uid]

    services_cfg = _load_yaml(SERVICES_YAML)
    services_cfg.setdefault("managed_services", [])
    services_cfg["daemon"] = services_cfg.get("daemon", {})
    services_cfg["daemon"]["tick_seconds"] = services_cfg["daemon"].get("tick_seconds", 10)
    services_cfg["daemon"]["dedup_repeat_seconds"] = services_cfg["daemon"].get("dedup_repeat_seconds", 300)
    services_cfg["daemon"]["api"] = {
        "enabled": api_enabled,
        "host": host,
        "port": port,
    }
    _save_yaml(SERVICES_YAML, services_cfg)

    plugins_cfg = _load_yaml(PLUGINS_YAML)
    plugins_cfg.setdefault("active", {})
    plugins_cfg["active"].setdefault("communication", {})
    plugins_cfg["active"]["communication"]["telegram"] = {
        "input": tg_enabled,
        "output": tg_enabled,
        "system_notifications": tg_enabled,
    }
    plugins_cfg.setdefault("plugins", {})
    if tg_enabled:
        plugins_cfg["plugins"]["telegram"] = {
            "token": tg_token,
            "chat_id": tg_chat_id,
            "allowed_user_ids": tg_user_ids,
            "approvals": {"enabled": True},
        }
    _save_yaml(PLUGINS_YAML, plugins_cfg)

    if not AGENTS_YAML.exists():
        _save_yaml(
            AGENTS_YAML,
            {
                "system_agents": {
                    "planner": {"model": "not-set", "provider": "not-set", "endpoint": "not-set"},
                    "router": {"model": "not-set", "provider": "not-set", "endpoint": "not-set"},
                },
                "custom_agents": {"agents": []},
            },
        )

    console.print("[green]Config written.[/green]")


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
        "args": [sys.executable, str(HERMESD_FILE)],
        "stdout": log_handle,
        "stderr": log_handle,
        "stdin": subprocess.DEVNULL,
        "cwd": str(PROJECT_ROOT),
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

    for _ in range(12):
        time.sleep(0.5)
        if is_daemon_running():
            console.print(f"[green]Daemon started.[/green] [dim](PID {get_daemon_pid()})[/dim]")
            return

    console.print("[red]Daemon did not start within 6 seconds.[/red]")
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


def render_status_bar():
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column("k", style="bold dim", width=10)
    table.add_column("v")

    if is_daemon_running():
        pid = get_daemon_pid()
        table.add_row("Daemon", f"[green]Running[/green] [dim](PID {pid})[/dim]")
        services_cfg = _load_yaml(SERVICES_YAML)
        api_cfg = services_cfg.get("daemon", {}).get("api", {})
        if api_cfg.get("enabled", True):
            host = api_cfg.get("host", "127.0.0.1")
            port = api_cfg.get("port", 5000)
            table.add_row("API", f"[cyan]http://{host}:{port}[/cyan]")
        else:
            table.add_row("API", "[dim]Disabled[/dim]")
    else:
        table.add_row("Daemon", "[red]Stopped[/red]")

    console.print(table)


def view_logs(lines: int = 50):
    console.print(Panel(f"[bold]Last {lines} lines — {LOG_FILE.name}[/bold]", box=box.SIMPLE))

    if not LOG_FILE.exists():
        console.print("[dim]No log file found yet.[/dim]")
        return

    content = _read_last_lines(LOG_FILE, lines)
    if not content.strip():
        console.print("[dim]Log file exists but is empty.[/dim]")
        return

    console.print(content.rstrip())
    _pause()


def pick_custom_agent() -> str | None:
    cfg = _load_yaml(AGENTS_YAML)
    agents = cfg.get("custom_agents", {}).get("agents", [])

    if not agents:
        console.print("[yellow]No custom agents defined in config/agents.yaml.[/yellow]")
        return None

    console.print("\n[bold]Available custom agents:[/bold]")
    for i, agent in enumerate(agents, 1):
        name = agent.get("name", f"agent-{i}")
        agent_type = agent.get("type", "?")
        enabled = agent.get("enabled", True)
        status = "[green]on[/green]" if enabled else "[red]off[/red]"
        console.print(f"  [bold]{i}[/bold]  {name} [dim]({agent_type})[/dim] {status}")

    console.print("  [bold]0[/bold]  Cancel")
    raw = Prompt.ask("Select agent", default="0").strip()
    if raw == "":
        return None
    try:
        idx = int(raw)
        if idx == 0:
            return None
        if 1 <= idx <= len(agents):
            return agents[idx - 1].get("name", f"agent-{idx}")
    except ValueError:
        pass

    console.print("[yellow]Invalid selection.[/yellow]")
    return None


def chat_loop(agent_name: str):
    console.print(
        Panel(
            f"[bold green]Chat — {agent_name}[/bold green]\n[dim]/back to return[/dim]",
            box=box.SIMPLE,
        )
    )

    if not is_daemon_running():
        console.print("[yellow]Daemon is not running. Start it first.[/yellow]")
        return

    while True:
        try:
            raw = Prompt.ask("[bold cyan]>[/bold cyan]", default="").strip()
        except (KeyboardInterrupt, EOFError):
            console.print()
            return

        if raw == "":
            continue
        if raw.lower() in {"/back", "/exit", "/quit", "q"}:
            return

        console.print(f"[dim][{agent_name}] Routing not connected yet. This is a stub for Milestone 2.[/dim]")


def show_home():
    console.clear()
    console.print(
        Panel(
            "[bold cyan]Hermes[/bold cyan] [dim]EVO-T1 AI Daemon[/dim]",
            box=box.DOUBLE_EDGE,
            padding=(0, 2),
        )
    )
    render_status_bar()
    console.print()
    console.print("  [bold cyan]1[/bold cyan]  Start Daemon")
    console.print("  [bold cyan]2[/bold cyan]  Stop Daemon")
    console.print("  [bold cyan]3[/bold cyan]  Chat: Server Agent")
    console.print("  [bold cyan]4[/bold cyan]  Chat: Custom Agent")
    console.print("  [bold cyan]5[/bold cyan]  View Logs")
    console.print("  [bold cyan]6[/bold cyan]  Reload Config")
    console.print()
    console.print("  [bold cyan]q[/bold cyan]  Quit Terminal [dim](daemon keeps running)[/dim]")
    console.print()


def main():
    if not configs_exist():
        run_wizard()
        _pause()

    while True:
        show_home()
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
            chat_loop("Server Agent")
        elif choice == "4":
            selected = pick_custom_agent()
            if selected:
                chat_loop(selected)
        elif choice == "5":
            view_logs()
        elif choice == "6":
            reload_config()
            _pause()
        elif choice in {"q", "quit", "exit"}:
            console.print("[dim]Detaching terminal. Daemon keeps running.[/dim]")
            return
        else:
            console.print("[yellow]Unknown option.[/yellow]")
            time.sleep(0.5)


if __name__ == "__main__":
    main()