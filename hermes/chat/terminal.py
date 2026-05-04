import logging
import sys
import traceback
from typing import Dict, List

from hermes.chat.orchestrator import Orchestrator
from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text


class HermesTerminal:
    def __init__(self):
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
        print("Initialising Hermes orchestrator…")
        try:
            self.orchestrator = Orchestrator(
                agents_cfg_path="config_test_values/agents.yaml",
                plugins_cfg_path="config_test_values/plugins.yaml",
            )
        except Exception as exc:
            logging.error("Failed to initialise orchestrator: %s", exc)
            sys.exit(1)
        self.console.clear()
        self._render_header("CHAT")

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        print("Run")
        self._init()

        while True:
            try:
                msg = self.console.input("[bold green]You >[/bold green] ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not msg:
                continue

            self._add_transcript("user", msg)

            try:
                result = self.orchestrator.run(msg)
                outcome = result["messages"][-1]
                assistant_parts = outcome.content
                if assistant_parts:
                    assistant_text = assistant_parts if isinstance(assistant_parts, str) else "\n".join(assistant_parts)
                    self._add_transcript("assistant", assistant_text)
                    self.console.print(f"[bold blue]Hermes >[/bold blue] {assistant_text}")
                else:
                    self._add_transcript("assistant", "")
                    self.console.print("[bold red]Hermes did not return a response.[/bold red]")

            except KeyboardInterrupt:
                self.console.print("\n[green]Exiting Hermes Terminal. Goodbye![/green]")
                sys.exit(0)

            except Exception as exc:
                self._add_transcript("error", str(exc))
                self.console.print(
                    Panel(
                        f"[red]Operator error:[/red] {exc}\n"
                        "[dim]Full trace written to errors.log[/dim]",
                        border_style="red",
                    )
                )
                if result != None:
                    self.console.print(
                        Panel(
                            "[green]Result:[/green]\n" + result,
                            border_style="yellow",
                        )
                    )
                self._log_error()
