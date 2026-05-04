import subprocess
import sys
from langchain_core.tools import tool




@tool("kill_process", description="Kill a process by name (e.g. 'notepad.exe') or PID.", return_direct=False)
def kill_process(identifier: str):
    """Kill a process by name (e.g. 'notepad.exe') or PID."""
    try:
        if sys.platform == "win32":
            if identifier.isdigit():
                args = ["taskkill", "/PID", identifier, "/F"]
            else:
                args = ["taskkill", "/IM", identifier, "/F"]
        else:
            if identifier.isdigit():
                args = ["kill", "-9", identifier]
            else:
                args = ["pkill", "-f", identifier]
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
        return {
            "identifier": identifier,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"error": str(e)}
