import os

from rich.panel import Panel

import session as session_store
import settings as settings_store


class BaseCommand:
    """Base class for chat slash commands."""

    names: tuple[str, ...] = ()
    help_text: str = ""
    order: int = 1000

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        raise NotImplementedError


class HelpCommand(BaseCommand):
    names = ("/help",)
    help_text = "Show this command list"
    order = 10

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        lines = []
        for command in dispatcher.registry:
            lines.append(f"[bold]{command.names[0]}[/bold] {command.help_text}")
        cmd_ctx["console"].print(Panel("\n".join(lines), title="Chat Commands", border_style="bright_blue"))
        return "CONTINUE"


class ClearCommand(BaseCommand):
    names = ("/clear",)
    help_text = "Clear chat window"
    order = 20

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        cmd_ctx["init_func"]("chat_top")
        return "CONTINUE"


class ReloadCommand(BaseCommand):
    names = ("/reload",)
    help_text = "Reload environment and operator"
    order = 30

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        msg = settings_store.reload_operator(cmd_ctx["env_path"], cmd_ctx["operator_module"], session_store.SESSION)
        cmd_ctx["console"].print(Panel(msg, border_style="green"))
        return "CONTINUE"


class SettingsCommand(BaseCommand):
    names = ("/settings",)
    help_text = "Open settings menu"
    order = 40

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        settings_store.run_settings(
            cmd_ctx["console"],
            cmd_ctx["read_key"],
            cmd_ctx["render_header"],
            cmd_ctx["env_path"],
            cmd_ctx["operator_module"],
            session_store.SESSION,
            cmd_ctx["default_model"],
            cmd_ctx["default_rpm"],
        )
        cmd_ctx["init_func"]("chat_top")
        return "CONTINUE"


class StatsCommand(BaseCommand):
    names = ("/stats",)
    help_text = "Open session dashboard"
    order = 50

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        session_store.render_session_dashboard(cmd_ctx["console"], cmd_ctx["render_header"])
        cmd_ctx["init_func"]("chat_top")
        return "CONTINUE"


class HistoryCommand(BaseCommand):
    names = ("/history",)
    help_text = "Show transcript; /history <query> to search"
    order = 60

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        session_store.show_history(cmd_ctx["console"], query=cmd_ctx["args"])
        return "CONTINUE"


class ResumeCommand(BaseCommand):
    names = ("/resume",)
    help_text = "Resume previous session; /resume <n> for nth"
    order = 70

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        n = int(cmd_ctx["args"]) if cmd_ctx["args"].isdigit() else 1
        sessions = session_store.list_sessions(cmd_ctx["base_dir"])
        candidates = [s for s in sessions if s != session_store.TRANSCRIPT_FILE]
        if not candidates:
            cmd_ctx["console"].print("[yellow]No previous sessions found.[/yellow]")
            return "CONTINUE"
        idx = min(n, len(candidates)) - 1
        target = candidates[idx]
        session_store.load_session(target)
        cmd_ctx["console"].print(
            Panel(
                f"Resumed session: [bold]{os.path.basename(target)}[/bold]\n"
                f"{len(session_store.CHAT_TRANSCRIPT)} entries loaded.",
                border_style="cyan",
            )
        )
        return "CONTINUE"


class SaveCommand(BaseCommand):
    names = ("/save",)
    help_text = "Export transcript to text file"
    order = 80

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        cmd_ctx["console"].print(Panel(session_store.save_transcript_to_file(cmd_ctx["base_dir"]), border_style="cyan"))
        return "CONTINUE"


class ExitCommand(BaseCommand):
    names = ("/exit", "/quit")
    help_text = "Return to main menu"
    order = 90

    def run(self, dispatcher: "ChatCommands", cmd_ctx: dict) -> str:
        return "EXIT"


class ChatCommands:
    """Registry-backed slash command dispatcher with class-based commands."""

    def __init__(self, ctx: dict):
        self.ctx = ctx
        self.registry = self._discover_commands()
        self.command_map: dict[str, BaseCommand] = {
            alias: command
            for command in self.registry
            for alias in command.names
        }

    def _discover_commands(self) -> list[BaseCommand]:
        """Instantiate all command plugins declared as BaseCommand subclasses."""
        commands = [cls() for cls in BaseCommand.__subclasses__() if cls.names]
        commands.sort(key=lambda c: c.order)
        return commands

    def execute(self, raw_command: str) -> str:
        """Dispatch a slash command via the registry. Never forwards to the operator."""
        parts = raw_command.strip().split(None, 1)
        verb = parts[0].lower()
        cmd_ctx = {**self.ctx, "args": parts[1].strip() if len(parts) > 1 else ""}

        command = self.command_map.get(verb)
        if command is None:
            cmd_ctx["console"].print("[red]Unknown command. Type /help[/red]")
            return "CONTINUE"
        return command.run(self, cmd_ctx)
