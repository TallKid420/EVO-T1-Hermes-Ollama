import os
import traceback
from datetime import datetime

from rich.panel import Panel

from commands import ChatCommands
import session as session_store


def _log_error(exc: Exception, base_dir: str) -> None:
    """Append the full traceback to errors.log so nothing is lost silently."""
    log_path = os.path.join(base_dir, "errors.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now().isoformat()} ---\n")
            f.write(traceback.format_exc())
    except OSError:
        pass  # Never let log-writing mask the original error


def run_chat(
    console,
    init_func,
    operator_module,
    env_path,
    read_key,
    render_header,
    base_dir,
    default_model,
    default_rpm,
):
    """Handle chat mode and slash-command interactions."""
    ctx = {
        "console": console,
        "init_func": init_func,
        "operator_module": operator_module,
        "env_path": env_path,
        "read_key": read_key,
        "render_header": render_header,
        "base_dir": base_dir,
        "default_model": default_model,
        "default_rpm": default_rpm,
    }
    commands = ChatCommands(ctx)

    init_func("chat_top")

    while True:
        try:
            msg = console.input("[bold green]You >[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not msg:
            continue

        if msg.startswith("/"):
            session_store.SESSION["commands"] += 1
            if commands.execute(msg) == "EXIT":
                break
            continue

        session_store.SESSION["prompts"] += 1
        session_store.SESSION["status"] = "Running operator plan"
        session_store.add_transcript("user", msg)

        try:
            operator_module.plan(msg)
            session_store.add_transcript("assistant", "Task handled by operator.")
            session_store.SESSION["status"] = "Ready"
        except operator_module.OperatorSlashCommand as slash_cmd:
            session_store.SESSION["commands"] += 1
            if commands.execute(slash_cmd.command) == "EXIT":
                break
            session_store.SESSION["status"] = "Ready"
        except KeyboardInterrupt:
            session_store.SESSION["status"] = "Interrupted"
            break
        except Exception as exc:
            session_store.SESSION["errors"] += 1
            session_store.SESSION["status"] = f"Error: {exc}"
            session_store.add_transcript("error", str(exc))
            console.print(
                Panel(
                    f"[red]Operator error:[/red] {exc}\n[dim]Full trace written to errors.log[/dim]",
                    border_style="red",
                )
            )
            _log_error(exc, base_dir)

