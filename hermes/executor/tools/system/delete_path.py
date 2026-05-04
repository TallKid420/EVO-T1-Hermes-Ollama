import os
import shutil
from hermes.executor.tool_helpers import _expand_path, _is_protected_path
from langchain_core.tools import tool




@tool("delete_path", description="Delete a file or directory tree.", return_direct=False)
def delete_path(path: str):
    """Delete a file or directory tree."""
    try:
        p = _expand_path(path)
        if not os.path.exists(p):
            return {"error": f"Path does not exist: {p}"}
        if _is_protected_path(p):
            return {"error": f"Refusing to delete protected path: {p}"}
        if os.path.isdir(p):
            shutil.rmtree(p)
            kind = "directory"
        else:
            os.remove(p)
            kind = "file"
        return {"deleted": path, "type": kind}
    except Exception as e:
        return {"error": str(e)}
