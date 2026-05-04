import subprocess
import sys
from langchain_core.tools import tool




@tool("ping_host", description="Ping a hostname or IP address and return latency stats.", return_direct=False)
def ping_host(host: str, count: int = 4):
    """Ping a hostname or IP address and return latency stats."""
    try:
        count = min(max(1, int(count)), 10)
        ping_flag = "-n" if sys.platform == "win32" else "-c"
        result = subprocess.run(
            ["ping", ping_flag, str(count), host],
            capture_output=True, text=True, timeout=30
        )
        return {"host": host, "output": result.stdout.strip(), "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"error": "Ping timed out"}
    except Exception as e:
        return {"error": str(e)}
