import glob
import json
import os
from datetime import datetime

from rich import box
from rich.panel import Panel
from rich.table import Table


SESSION = {
    "started": datetime.now(),
    "prompts": 0,
    "commands": 0,
    "errors": 0,
    "status": "Ready",
}

CHAT_TRANSCRIPT: list[dict] = []
TRANSCRIPT_FILE: str | None = None


def init_transcript(base_dir: str) -> None:
    """Create a fresh JSONL session file and set it as the active transcript."""
    global TRANSCRIPT_FILE, CHAT_TRANSCRIPT
    out_dir = os.path.join(base_dir, "transcripts")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    TRANSCRIPT_FILE = os.path.join(out_dir, f"session_{stamp}.jsonl")
    CHAT_TRANSCRIPT = []


def list_sessions(base_dir: str, limit: int = 10) -> list[str]:
    """Return paths to the most recent session JSONL files, newest first."""
    out_dir = os.path.join(base_dir, "transcripts")
    files = sorted(glob.glob(os.path.join(out_dir, "session_*.jsonl")), reverse=True)
    return files[:limit]


def load_session(path: str) -> bool:
    """Load a previous JSONL session into CHAT_TRANSCRIPT. Future writes go to that file."""
    global TRANSCRIPT_FILE, CHAT_TRANSCRIPT
    if not os.path.exists(path):
        return False
    entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                try:
                    entries.append(json.loads(stripped))
                except json.JSONDecodeError:
                    pass
    CHAT_TRANSCRIPT = entries
    TRANSCRIPT_FILE = path
    return True


def search_history(query: str, limit: int = 20) -> list[dict]:
    """Return the last *limit* transcript entries whose content contains *query*."""
    q = query.lower()
    return [e for e in CHAT_TRANSCRIPT if q in e["content"].lower()][-limit:]


def add_transcript(role: str, content: str) -> None:
    entry = {"ts": datetime.now().strftime("%H:%M:%S"), "role": role, "content": content}
    CHAT_TRANSCRIPT.append(entry)
    if TRANSCRIPT_FILE:
        with open(TRANSCRIPT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def save_transcript_to_file(base_dir: str) -> str:
    if not CHAT_TRANSCRIPT:
        return "Failed: Transcript is empty."

    out_dir = os.path.join(base_dir, "transcripts")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(out_dir, f"export_{stamp}.txt")

    with open(out_path, "w", encoding="utf-8") as out:
        for item in CHAT_TRANSCRIPT:
            out.write(f"[{item['ts']}] {item['role']}: {item['content']}\n")

    return f"Saved transcript: {out_path}"


def show_history(console, query: str = "") -> None:
    if query:
        items = search_history(query)
        label = f"Search: {query!r}"
    else:
        items = CHAT_TRANSCRIPT[-12:]
        label = "Recent Transcript"

    if not items:
        console.print(f"[dim]No results{' for ' + repr(query) if query else ''}.[/dim]")
        return

    table = Table(show_header=True, box=box.SIMPLE)
    table.add_column("Time", width=10)
    table.add_column("Role", width=10)
    table.add_column("Content", width=80)
    for item in items:
        table.add_row(item["ts"], item["role"], item["content"][:80].replace("\n", " "))
    console.print(Panel(table, title=label, border_style="blue"))


def render_session_dashboard(console, render_header):
    console.clear()
    render_header("SESSION", "Live telemetry and recent activity")

    uptime = datetime.now() - SESSION["started"]
    uptime_text = str(uptime).split(".")[0]

    table = Table(show_header=True, box=box.ROUNDED, border_style="bright_blue")
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Uptime", uptime_text)
    table.add_row("Prompts Sent", str(SESSION["prompts"]))
    table.add_row("Slash Commands", str(SESSION["commands"]))
    table.add_row("Errors", str(SESSION["errors"]))
    table.add_row("Status", SESSION["status"])
    table.add_row("Transcript Entries", str(len(CHAT_TRANSCRIPT)))
    if TRANSCRIPT_FILE:
        table.add_row("Session File", os.path.basename(TRANSCRIPT_FILE))
    console.print(table)

    recent = CHAT_TRANSCRIPT[-8:]
    if recent:
        recent_table = Table(show_header=True, box=box.SIMPLE_HEAD)
        recent_table.add_column("Time", width=10)
        recent_table.add_column("Role", width=10)
        recent_table.add_column("Content", width=70)
        for item in recent:
            snippet = item["content"][:70].replace("\n", " ")
            recent_table.add_row(item["ts"], item["role"], snippet)
        console.print(Panel(recent_table, title="Recent Transcript", border_style="blue"))

    console.input("\n[dim]Press Enter to return...[/dim]")
