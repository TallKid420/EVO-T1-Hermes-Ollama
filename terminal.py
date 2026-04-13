import logging
import msvcrt
import os
import sys

import chat
import hermes_operator as operator
import session as session_store
import settings as settings_store
from rich import box
from rich.align import Align
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Defaults
defualt_model = "openai/gpt-oss-120b"
defualt_rpm = "20"
APP_VERSION = "2.0"
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

# Rich console / logging
console = Console()
INFO_FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=INFO_FORMAT, datefmt="[%X]", handlers=[RichHandler()]
)
log = logging.getLogger("rich")

# Main menu
ACTIONS = [
    ("Chat", "Start a conversation with Hermes", None),
    ("Settings", "Configure Groq and operator options", None),
    ("Session", "View session stats and recent history", None),
    ("About", "See shortcuts and available features", None),
    ("Exit", "Quit the application", lambda: sys.exit(0)),
]


def read_key():
    """Read one keypress and normalize common control keys on Windows."""
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        return {"H": "UP", "P": "DOWN"}.get(msvcrt.getwch(), "OTHER")
    if ch == "\x03":
        raise KeyboardInterrupt
    return "ENTER" if ch in ("\r", "\n") else ch


def render_header(title, subtitle=""):
    text = Text(title, style="bold cyan", justify="center")
    panel_content = Align.center(text)
    console.print(Panel(panel_content, style="cyan dim", padding=(1, 4)))
    if subtitle:
        console.print(Align.center(Text(subtitle, style="dim")))


def render_menu(sel):
    """Render the main action selector."""
    console.clear()
    settings = settings_store.load_settings(ENV_PATH)
    subtitle = (
        f"v{APP_VERSION}   model: {settings.get('GROQ_MODEL', defualt_model)}   "
        f"rpm: {settings.get('GROQ_RPM_LIMIT', defualt_rpm)}"
    )
    render_header("HERMES", subtitle)

    table = Table(
        show_header=False,
        box=box.ROUNDED,
        border_style="bright_blue",
        padding=(0, 2),
        expand=False,
    )
    table.add_column(width=3)
    table.add_column(width=14)
    table.add_column(width=44)

    for i, (action, desc, _) in enumerate(ACTIONS):
        if i == sel:
            table.add_row(
                Text("▶", style="bold yellow"),
                Text(action, style="bold yellow on dark_blue"),
                Text(desc, style="white on dark_blue"),
            )
        else:
            table.add_row(
                Text(" "),
                Text(action, style="bold white"),
                Text(desc, style="dim white"),
            )

    console.print(Align.center(table))
    console.print(Align.center(Text("\n↑ ↓ Navigate   Enter Select   Ctrl+C Exit", style="dim")))


def run_about():
    console.clear()
    render_header("ABOUT HERMES", "Decked terminal mode")
    console.print(
        Panel(
            "[bold]Main Features[/bold]\n"
            "• Arrow-key navigation\n"
            "• Interactive settings with live reload\n"
            "• Connection testing and defaults reset\n"
            "• Session telemetry dashboard\n"
            "• Transcript history and export\n\n"
            "[bold]Chat Commands[/bold]\n"
            "/help, /clear, /reload, /settings, /stats\n"
            "/history [query], /resume [n], /save, /exit",
            border_style="cyan",
        )
    )
    console.input("\n[dim]Press Enter to return...[/dim]")


def run_chat_screen():
    chat.run_chat(
        console,
        init,
        operator,
        ENV_PATH,
        read_key,
        render_header,
        os.path.dirname(__file__),
        defualt_model,
        defualt_rpm,
    )


def run_settings_screen():
    settings_store.run_settings(
        console,
        read_key,
        render_header,
        ENV_PATH,
        operator,
        session_store.SESSION,
        defualt_model,
        defualt_rpm,
    )


def run_session_screen():
    session_store.render_session_dashboard(console, render_header)


# HANDLERS maps menu selections to corresponding actions
HANDLERS = [
    run_chat_screen,
    run_settings_screen,
    run_session_screen,
    run_about,
    lambda: (console.print("\n[dim]Goodbye.[/dim]"), sys.exit(0)),
]


def init(mode: str = None):
    if mode in {"chat_top", None}:
        console.clear()
        render_header("CHAT", "Type /help for commands   Type /exit to return")

    if mode in {"start_terminal", None}:
        log.info("Starting Terminal")
        log.info("Fetching .env")

        validated_settings, validation_errors = settings_store.load_settings_with_validation(
            ENV_PATH,
            strict_required=True,
        )
        for err in validation_errors:
            log.warning(f"Settings validation: {err}")

        # Seed process env with validated values so operator.setup() reads a safe config.
        for key, value in validated_settings.items():
            os.environ[key] = value

        try:
            state = operator.setup(ENV_PATH)
        except Exception as exc:
            log.critical(f"Error: {exc}")
            raise SystemExit(1)

        if os.getenv("GROQ_MODEL") is None:
            log.warning(f"Model not set in .env, using defualt {defualt_model}")
        if os.getenv("GROQ_RPM_LIMIT") is None:
            log.warning(f"rpm not set in .env, using defualt {defualt_rpm}")

        log.info("API key retrived")
        log.info(f"Operator ready - model: {state['model']}")
        log.info(f"Compound routing model: {state['compound_model']} (via compound_* tools)")
        session_store.init_transcript(os.path.dirname(__file__))
        session_store.SESSION["status"] = f"Ready ({state['model']})"


def main():
    """Main event loop for the terminal menu."""
    init("start_terminal")
    sel = 0

    while True:
        render_menu(sel)

        try:
            key = read_key()
        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye.[/dim]")
            sys.exit(0)

        if key == "UP":
            sel = (sel - 1) % len(ACTIONS)
        elif key == "DOWN":
            sel = (sel + 1) % len(ACTIONS)
        elif key == "ENTER":
            HANDLERS[sel]()


if __name__ == "__main__":
    main()
