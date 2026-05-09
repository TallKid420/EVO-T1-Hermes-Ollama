import logging
import sys
import traceback
from typing import Dict, List
import httpx

from hermes.chat.orchestrator import Orchestrator
from hermes.agents.base_agent import BaseAgent
from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text


class HermesTerminal:
    def __init__(self, agent: BaseAgent):
        self.agent = agent
        print("Initialising Hermes orchestrator…")
        try:
            self.orchestrator = Orchestrator(self.agent)
        except Exception as exc:
            logging.error("Failed to initialise orchestrator: %s", exc)
            sys.exit(1)
        self.transcript: List[Dict[str, str]] = []
        self.console = Console()
        logging.basicConfig(
            level="NOTSET", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
        )
        self.log = logging.getLogger("rich")

    # ── Header ────────────────────────────────────────────────────────────────
    def _render_header(self, title: str, subtitle: str = ""):
        text = Text(title, style="bold cyan", justify="center")
        self.console.print(Panel(Align.center(text), style="cyan dim", padding=(1, 4)))
        if subtitle:
            self.console.print(Align.center(Text(subtitle, style="dim")))

    # ── Transcript ────────────────────────────────────────────────────────────
    def _add_transcript(self, role: str, text: str) -> None:
        self.transcript.append({"role": role, "text": text})

    # ── Error logger ──────────────────────────────────────────────────────────
    def _log_error(self) -> None:
        self.console.print(
            Panel(
                "[yellow]Traceback:[/yellow]\n" + traceback.format_exc(),
                border_style="yellow",
            )
        )

    # ── Init ──────────────────────────────────────────────────────────────────
    def _init(self):
        self.log.info("Starting Terminal")
        self.console.clear()
        self._render_header("CHAT")

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        self._init()
        result = None

        while True:
            try:
                msg = self.console.input("[bold green]You >[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not msg:
                continue

            if msg.lower() == "/exit":
                self.console.print("[green]Exiting Hermes Terminal. Goodbye![/green]")
                break

            self._add_transcript("user", msg)

            try:
                result = self.orchestrator.run(msg)
                if isinstance(result, dict) and result.get("error"):
                    self.console.print(
                        Panel(
                            f"[red]Connection Error:[/red] {result['message']}",
                            border_style="red",
                        )
                    )
                    continue

                outcome = result["messages"][-1]
                assistant_parts = outcome.content

                if assistant_parts:
                    assistant_text = (
                        assistant_parts 
                        if isinstance(assistant_parts, str) 
                        else "\n".join(assistant_parts)
                    )
                    self._add_transcript("assistant", assistant_text)
                    self.console.print(f"[bold blue]Hermes >[/bold blue] {assistant_text}")
                else:
                    self._add_transcript("assistant", "")
                    self.console.print("[bold red]Hermes did not return a response.[/bold red]")

            except KeyboardInterrupt:
                self.console.print("\n[green]Exiting Hermes Terminal. Goodbye![/green]")
                sys.exit(0)

            except httpx.ConnectError as exc:
                self._add_transcript("error", str(exc))
                self.console.print(
                    Panel(
                        f"[red]Operator error:[/red] {exc}\n"
                        "[dim]Full trace written to errors.log[/dim]",
                        border_style="red",
                    )
                )
                self._log_error()

            except Exception as exc:
                self._add_transcript("error", str(exc))
                self.console.print(
                    Panel(
                        f"[red]Operator error:[/red] {exc}\n"
                        "[dim]Full trace written to errors.log[/dim]",
                        border_style="red",
                    )
                )
                if result is not None:
                    self.console.print(
                        Panel(
                            "[green]Result:[/green]\n" + str(result),
                            border_style="yellow",
                        )
                    )
                self._log_error()
