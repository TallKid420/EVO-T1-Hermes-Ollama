import os
from langchain_core.tools import tool




@tool("get_environment_variable", description="Read the value of an environment variable.", return_direct=False)
def get_environment_variable(name: str):
    """Read the value of an environment variable."""
    value = os.environ.get(name)
    if value is None:
        return {"error": f"Environment variable '{name}' not found"}
    return {"name": name, "value": value}
