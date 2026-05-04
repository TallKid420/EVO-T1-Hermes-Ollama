import math
from langchain_core.tools import tool




@tool("calculate", description="Safely evaluate a mathematical expression.", return_direct=False)
def calculate(expression: str):
    """Safely evaluate a mathematical expression."""
    safe_globals = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
    safe_globals["abs"] = abs
    safe_globals["round"] = round
    safe_globals["min"] = min
    safe_globals["max"] = max
    try:
        result = eval(expression, {"__builtins__": {}}, safe_globals)  # noqa: S307
        return {"expression": expression, "result": result}
    except Exception as e:
        return {"error": str(e)}
