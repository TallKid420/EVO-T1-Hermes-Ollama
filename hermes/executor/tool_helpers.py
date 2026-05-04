import os
import sys
import re


def _expand_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _is_protected_path(path: str) -> bool:
    """Prevent dangerous operations on critical roots/directories."""
    p = _expand_path(path)
    drive = os.path.splitdrive(p)[0]
    protected_exact = {
        p.lower() for p in {
            os.path.abspath(os.sep),
            os.path.abspath(os.getcwd()),
            os.path.abspath(os.path.expanduser("~")),
            os.path.abspath(os.path.join(os.path.expanduser("~"), "Downloads")),
        }
    }
    if drive:
        protected_exact.add((drive + "\\").lower())

    pl = p.lower()
    if pl in protected_exact:
        return True

    protected_markers = (
        "\\windows",
        "\\program files",
        "\\program files (x86)",
        "\\programdata",
        "\\appdata\\local\\programs",
    )
    if sys.platform == "win32" and any(marker in pl for marker in protected_markers):
        return True

    unix_markers = (
        "/bin",
        "/sbin",
        "/usr/bin",
        "/usr/sbin",
        "/usr/local/bin",
        "/etc",
        "/root",
        "/boot",
        "/sys",
        "/proc",
        "/dev",
        "/var/log",
    )
    if sys.platform != "win32" and any(marker in pl for marker in unix_markers):
        return True

    return False


def _normalize_shell_command(command: str) -> str:
    """Strip shell wrappers when running on Windows."""
    cmd = command.strip()
    if sys.platform == "win32":
        cmd = re.sub(r"^powershell(\.exe)?\s+-NoProfile\s+-NonInteractive\s+-Command\s+", "", cmd, flags=re.IGNORECASE)
        cmd = re.sub(r"^powershell(\.exe)?\s+-Command\s+", "", cmd, flags=re.IGNORECASE)
    return cmd


def _is_safe_parent_path(path: str) -> bool:
    p = _expand_path(path)
    parent = os.path.dirname(p)
    if not parent:
        return False
    workspace = os.path.abspath(os.getcwd())
    if _is_protected_path(parent) and os.path.abspath(parent) != workspace:
        return False
    try:
        common = os.path.commonpath([workspace, p])
    except ValueError:
        return False
    return common == workspace
