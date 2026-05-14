"""
hermes/runtime/state.py
Daemon PID lock and status detection.
"""
from pathlib import Path
import os
import tempfile

PID_FILE = Path("/tmp/hermes.pid") if os.name != "nt" else Path(tempfile.gettempdir()) / "hermes.pid"


def write_pid():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_pid():
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def is_daemon_running() -> bool:
    pid = read_pid()
    if pid is None:
        return False
    try:
        # Signal 0 = check if process exists, no actual signal sent
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        clear_pid()
        return False
    except PermissionError:
        # Process exists but owned by another user
        return True
    except OSError:
        # Handles Windows-specific invalid process states
        clear_pid()
        return False


def get_daemon_pid() -> int | None:
    if is_daemon_running():
        return read_pid()
    else:
        return None