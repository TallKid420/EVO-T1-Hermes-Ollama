from langchain_core.tools import tool
@tool("sort_list", description="Sort a list of numbers or strings. order: 'asc' or 'desc'.", return_direct=False)
def sort_list(items: list, order: str = "asc"):
    """Sort a list of numbers or strings. order: 'asc' or 'desc'."""
    try:
        sorted_items = sorted(items, reverse=(order.lower() == "desc"))
        return {"original": items, "sorted": sorted_items, "order": order}
    except TypeError as e:
        return {"error": str(e)}
