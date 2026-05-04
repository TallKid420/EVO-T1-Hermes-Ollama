import os
import subprocess
import sys
from langchain_core.tools import tool




@tool("open_file", description="Open a file or URL with its default application.", return_direct=False)
def open_file(path: str):
    """Open a file or URL with its default application."""
    try:
        target = os.path.expanduser(path)
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.run(["open", target], capture_output=True, text=True, timeout=10)
        else:
            subprocess.run(["xdg-open", target], capture_output=True, text=True, timeout=10)
        return {"opened": path}
    except Exception as e:
        return {"error": str(e)}
