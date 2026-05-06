"""
config/wizard.py
First-run setup wizard using Rich.
"""
import socket
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
from config.manager import (
    DAEMON_YAML, SERVICES_YAML, AGENTS_YAML, PLUGINS_YAML,
    missing_configs, save
)

console = Console()


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex((host, port)) == 0


def _prompt_flask_config() -> dict:
    enabled = Confirm.ask("  Enable Flask API?", default=True)
    if not enabled:
        return {"api": {"enabled": False, "host": "127.0.0.1", "port": 5000}}

    host = Prompt.ask("  API host", default="127.0.0.1")
    port = int(Prompt.ask("  API port", default="5000"))

    while _port_in_use(host, port):
        console.print(f"  [bold red]Port {port} is already in use.[/bold red]")
        port = int(Prompt.ask("  Choose a different port", default=str(port + 1)))

    return {"api": {"enabled": True, "host": host, "port": port}}


def _write_default_services():
    data = {
        "managed_services": {
            "hermes": {
                "systemd_unit": "hermes.service",
                "auto_restart": False,
                "max_restarts_per_hour": 3,
                "cooldown_seconds": 60,
            }
        },
        "daemon": {
            "tick_seconds": 10,
            "dedup_repeat_seconds": 300,
        }
    }
    save(SERVICES_YAML, data)


def _write_default_agents():
    data = {
        "system_agents": {
            "server": {
                "enabled": True,
                "model": "hermes3",
                "provider": "ollama",
                "command_policy": "ops_safe",
                "allowed_commands": [],
            }
        },
        "custom_agents": {}
    }
    save(AGENTS_YAML, data)


def _write_default_plugins():
    data = {"plugins": {}}
    save(PLUGINS_YAML, data)


def run_wizard():
    console.print(Panel(
        "[bold cyan]Hermes First-Run Setup[/bold cyan]\n"
        "[dim]This wizard will create your config files.[/dim]",
        box=box.DOUBLE_EDGE
    ))

    missing = missing_configs()
    if missing:
        console.print(f"\n[yellow]Missing config files:[/yellow]")
        for m in missing:
            console.print(f"  [dim]{m}[/dim]")
        console.print()

    # Flask / API config
    daemon_cfg = _prompt_flask_config()

    # Telegram
    telegram_enabled = Confirm.ask("  Enable Telegram notifications/approvals?", default=False)
    if telegram_enabled:
        token = Prompt.ask("  Telegram Bot Token")
        admin_id = Prompt.ask("  Your Telegram User ID (for approvals)")
        daemon_cfg["telegram"] = {
            "enabled": True,
            "bot_token": token,
            "admin_ids": [int(admin_id)],
        }
    else:
        daemon_cfg["telegram"] = {"enabled": False}

    save(DAEMON_YAML, daemon_cfg)

    if SERVICES_YAML in missing:
        _write_default_services()
    if AGENTS_YAML in missing:
        _write_default_agents()
    if PLUGINS_YAML in missing:
        _write_default_plugins()

    console.print("\n[bold green]✓ Config files written.[/bold green]\n")