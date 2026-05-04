import random
from langchain_core.tools import tool




@tool("roll_dice", description="Roll one or more dice with a given number of sides.", return_direct=False)
def roll_dice(sides: int = 6, count: int = 1):
    """Roll one or more dice with a given number of sides."""
    sides = max(2, int(sides))
    count = min(max(1, int(count)), 100)
    rolls = [random.randint(1, sides) for _ in range(count)]
    return {"sides": sides, "count": count, "rolls": rolls, "total": sum(rolls)}
