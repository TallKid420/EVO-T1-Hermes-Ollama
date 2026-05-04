import os
from hermes.executor.tool_helpers import _expand_path, _is_protected_path, _is_safe_parent_path
from langchain_core.tools import tool




@tool("write_file_text", description="Write (or append) text to a file. Creates parent directories if needed.", return_direct=False)
def write_file_text(path: str, content: str, append: bool = False):
    """Write (or append) text to a file. Creates parent directories if needed."""
    try:
        p = _expand_path(path)
        if _is_protected_path(p):
            return {"error": f"Refusing to write to protected path: {p}"}
        if not _is_safe_parent_path(p):
            return {"error": f"Refusing to write outside workspace-safe parent path: {p}"}
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        return {"path": path, "bytes_written": len(content.encode()), "mode": "append" if append else "overwrite"}
    except Exception as e:
        return {"error": str(e)}
