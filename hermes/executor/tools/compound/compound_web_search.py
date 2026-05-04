from hermes.executor.tools.compound.compound_search import _call_compound
from langchain_core.tools import tool




@tool("compound_web_search", description="Force a web search style request through groq/compound.", return_direct=False)
def compound_web_search(query: str, max_results: int = 5) -> dict:
    """Force a web search style request through groq/compound."""
    q = str(query).strip()
    if not q:
        return {"error": "query is required"}
    max_results = min(max(1, int(max_results)), 10)
    prompt = (
        "Use web search to answer this query with current information. "
        f"Return up to {max_results} concise results with source links when possible.\n\n"
        f"Query: {q}"
    )
    return _call_compound(prompt)
