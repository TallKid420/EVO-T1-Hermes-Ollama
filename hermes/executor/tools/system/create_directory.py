import os
from hermes.executor.tool_helpers import _expand_path, _is_protected_path
from langchain_core.tools import tool




@tool("create_directory", description="Create a directory (and any missing parents).", return_direct=False)
def create_directory(path: str):
    """Create a directory (and any missing parents)."""
    try:
        p = _expand_path(path)
        if _is_protected_path(p):
            return {"error": f"Refusing to create protected path directly: {p}"}
        os.makedirs(p, exist_ok=True)
        return {"path": path, "created": True}
    except Exception as e:
        return {"error": str(e)}
