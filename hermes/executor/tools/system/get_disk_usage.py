import os
import shutil
from langchain_core.tools import tool




@tool("get_disk_usage", description="Return total, used, and free disk space for a drive or path.", return_direct=False)
def get_disk_usage(path: str = "C:\\"):
    """Return total, used, and free disk space for a drive or path."""
    try:
        usage = shutil.disk_usage(os.path.expanduser(path))
        gb = 1024 ** 3
        return {
            "path": path,
            "total_gb": round(usage.total / gb, 2),
            "used_gb": round(usage.used / gb, 2),
            "free_gb": round(usage.free / gb, 2),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception as e:
        return {"error": str(e)}
