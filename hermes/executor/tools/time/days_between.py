from datetime import date
from langchain_core.tools import tool




@tool("days_between", description="Return the number of days between two ISO dates (YYYY-MM-DD).", return_direct=False)
def days_between(date1: str, date2: str):
    """Return the number of days between two ISO dates (YYYY-MM-DD)."""
    try:
        d1 = date.fromisoformat(date1)
        d2 = date.fromisoformat(date2)
        delta = abs((d2 - d1).days)
        return {"date1": date1, "date2": date2, "days": delta}
    except ValueError as e:
        return {"error": str(e)}
