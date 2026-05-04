import subprocess
import sys
from hermes.executor.tool_helpers import _normalize_shell_command
from langchain_core.tools import tool




@tool("run_shell_command", description="Run a shell command and return stdout/stderr.", return_direct=False)
def run_shell_command(command: str, timeout: int = 30):
    """Run a shell command and return stdout/stderr."""
    try:
        normalized = _normalize_shell_command(command)
        timeout = min(max(1, int(timeout)), 120)
        if sys.platform == "win32":
            args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", normalized]
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        else:
            result = subprocess.run(normalized, capture_output=True, text=True, timeout=timeout, shell=True)
        return {
            "command": normalized,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}
