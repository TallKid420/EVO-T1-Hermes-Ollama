import subprocess
import sys
from langchain_core.tools import tool




@tool("get_running_processes", description="List running processes with PID and memory usage.", return_direct=False)
def get_running_processes():
    """List running processes with PID and memory usage."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=15
            )
            processes = []
            for line in result.stdout.strip().splitlines()[:60]:
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 5:
                    processes.append({"name": parts[0], "pid": parts[1], "memory": parts[4]})
            return {"count": len(processes), "processes": processes}

        result = subprocess.run(
            ["ps", "-eo", "pid=,comm=,%mem=", "--sort=-%mem"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        processes = []
        for line in result.stdout.strip().splitlines()[:60]:
            parts = line.split(None, 2)
            if len(parts) >= 3:
                pid, name, mem = parts
                processes.append({"name": name, "pid": pid, "memory": f"{mem}%"})
        return {"count": len(processes), "processes": processes}
    except Exception as e:
        return {"error": str(e)}
