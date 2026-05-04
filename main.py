#!/usr/bin/env python3
"""
Rich Chat Window with Command Handler
"""

import sys, shlex
from hermes.cli import hermesctl
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt
from rich.table import Table
from rich import box

console = Console()

# ── Rendering ─────────────────────────────────────────────────────────────────

def render_message(entry: dict):
    role = entry["role"]
    text = entry["text"]

    match role:
        case "user":
            msg = Text()
            msg.append("You: ", style="bold cyan")
            msg.append(text)
            console.print(msg)
        case "system":
            console.print(Panel(text, style="bold yellow", box=box.SIMPLE))
        case "error":
            console.print(f"[bold red]✗[/bold red] {text}")
        case _:
            msg = Text()
            msg.append(f"{role}: ", style="bold green")
            msg.append(text)
            console.print(msg)

# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold]Chat Window[/bold]  [dim]Type /help for commands[/dim]",
        style="bold blue", box=box.DOUBLE_EDGE
    ))

    while True:
        try:
            raw = Prompt.ask("\n[bold cyan]>[/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            render_message({"role": "system", "text": "Exiting..."})
            sys.exit(0)

        if not raw:
            continue

        if raw.startswith("/"):
            try:
                hermesctl.main(*shlex.split(raw[1:]))
            except SystemExit:
                pass
        else:
            render_message({"role": "user", "text": "Server Agent not implemented."})

if __name__ == "__main__":
    main()