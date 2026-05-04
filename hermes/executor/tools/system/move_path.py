import os
import shutil
from hermes.executor.tool_helpers import _expand_path, _is_protected_path
from langchain_core.tools import tool




@tool("move_path", description="Move or rename a file or directory.", return_direct=False)
def move_path(source: str, destination: str):
    """Move or rename a file or directory."""
    try:
        src = _expand_path(source)
        dst = _expand_path(destination)
        if not os.path.exists(src):
            return {"error": f"Source does not exist: {src}"}
        if _is_protected_path(src):
            return {"error": f"Refusing to move protected source path: {src}"}
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.move(src, dst)
        return {"source": source, "destination": destination}
    except Exception as e:
        return {"error": str(e)}
