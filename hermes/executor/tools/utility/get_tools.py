import inspect
import hermes.executor as executor_package
from langchain_core.tools import tool




@tool("get_tools", description="Return the currently available tool names and descriptions.", return_direct=False)
def get_tools():
    """Return the currently available tool names and descriptions."""
    tools = []
    for name, fn in getattr(executor_package, "EXECUTOR", {}).items():
        if not callable(fn) or name.startswith("_"):
            continue
        description = inspect.getdoc(fn) or ""
        tools.append({"name": name, "description": description.strip().split("Args:", 1)[0].strip()})
    return {"count": len(tools), "tools": tools}
