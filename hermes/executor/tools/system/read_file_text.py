import os
from langchain_core.tools import tool




@tool("read_file_text", description="Read the text content of a file, capped at max_chars characters.", return_direct=False)
def read_file_text(path: str, max_chars: int = 8000):
    """Read the text content of a file, capped at max_chars characters."""
    try:
        with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        truncated = os.path.getsize(os.path.expanduser(path)) > max_chars
        return {"path": path, "content": content, "truncated": truncated}
    except Exception as e:
        return {"error": str(e)}
