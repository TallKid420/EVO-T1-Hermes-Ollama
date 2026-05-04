import os
import shutil
from hermes.executor.tool_helpers import _expand_path, _is_protected_path
from langchain_core.tools import tool




@tool("copy_file", description="Copy a file to a destination path.", return_direct=False)
def copy_file(source: str, destination: str):
    """Copy a file to a destination path."""
    try:
        src = _expand_path(source)
        dst = _expand_path(destination)
        if not os.path.isfile(src):
            return {"error": f"Source file does not exist: {src}"}
        if _is_protected_path(src):
            return {"error": f"Refusing to copy protected source path: {src}"}
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        shutil.copy2(src, dst)
        return {"source": source, "destination": destination}
    except Exception as e:
        return {"error": str(e)}
