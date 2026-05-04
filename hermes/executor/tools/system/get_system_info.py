import platform
from langchain_core.tools import tool




@tool("get_system_info", description="Return basic OS, CPU architecture, hostname, and Python version info.", return_direct=False)
def get_system_info():
    """Return basic OS, CPU architecture, hostname, and Python version info."""
    uname = platform.uname()
    return {
        "os": uname.system,
        "os_version": uname.version,
        "release": uname.release,
        "machine": uname.machine,
        "hostname": uname.node,
        "python_version": platform.python_version(),
        "processor": uname.processor,
    }
