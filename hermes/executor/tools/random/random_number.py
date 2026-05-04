import random
from langchain_core.tools import tool




@tool("random_number", description="Generate a random float between min_value and max_value.", return_direct=False)
def random_number(min_value: float = 0, max_value: float = 100):
    """Generate a random float between min_value and max_value."""
    if min_value > max_value:
        return {"error": "min_value must be ≤ max_value"}
    result = random.uniform(min_value, max_value)
    return {"min": min_value, "max": max_value, "result": round(result, 6)}
