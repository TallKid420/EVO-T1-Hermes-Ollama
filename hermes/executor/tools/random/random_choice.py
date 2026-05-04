import random
from langchain_core.tools import tool




@tool("random_choice", description="Pick a random element from a list.", return_direct=False)
def random_choice(items: list):
    """Pick a random element from a list."""
    if not items:
        return {"error": "List is empty"}
    choice = random.choice(items)
    return {"items": items, "choice": choice}
