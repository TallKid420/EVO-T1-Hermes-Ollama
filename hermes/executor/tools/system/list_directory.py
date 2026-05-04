import os
from langchain_core.tools import tool




@tool("list_directory", description="List files and subdirectories inside a folder.", return_direct=False)
def list_directory(path: str):
    """List files and subdirectories inside a folder."""
    try:
        entries = []
        with os.scandir(os.path.expanduser(path)) as it:
            for e in sorted(it, key=lambda x: (not x.is_dir(), x.name.lower())):
                stat = e.stat(follow_symlinks=False)
                entries.append({
                    "name": e.name,
                    "type": "dir" if e.is_dir() else "file",
                    "size_bytes": stat.st_size if e.is_file() else None,
                })
        return {"path": path, "count": len(entries), "entries": entries}
    except Exception as e:
        return {"error": str(e)}
