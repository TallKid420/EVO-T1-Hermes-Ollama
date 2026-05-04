import os
from langchain_core.tools import tool




@tool("find_files", description="Find files by glob pattern in a directory and return full paths.", return_direct=False)
def find_files(pattern: str, directory: str = "~", recursive: bool = True, max_results: int = 20):
    """Find files by glob pattern in a directory and return full paths."""
    try:
        base_dir = os.path.abspath(os.path.expanduser(directory))
        if not os.path.isdir(base_dir):
            return {"error": f"Directory not found: {base_dir}"}
        max_results = min(max(1, int(max_results)), 200)
        matcher = "**/*" if recursive else "*"
        import fnmatch

        results: list[str] = []
        for root, _, files in os.walk(base_dir):
            for name in files:
                if fnmatch.fnmatch(name.lower(), pattern.lower()):
                    results.append(os.path.join(root, name))
                    if len(results) >= max_results:
                        return {"directory": base_dir, "pattern": pattern, "count": len(results), "paths": results}
            if not recursive:
                break
        return {"directory": base_dir, "pattern": pattern, "count": len(results), "paths": results}
    except Exception as e:
        return {"error": str(e)}
