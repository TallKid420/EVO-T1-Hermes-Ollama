from hermes.executor.tools.compound.compound_search import _call_compound
from langchain_core.tools import tool




@tool("compound_wolfram", description="Ask groq/compound to use Wolfram Alpha for math/science knowledge queries.", return_direct=False)
def compound_wolfram(query: str) -> dict:
    """Ask groq/compound to use Wolfram Alpha for math/science knowledge queries."""
    q = str(query).strip()
    if not q:
        return {"error": "query is required"}
    prompt = (
        "Use Wolfram Alpha to answer this precisely. "
        "Return key result values and units when relevant.\n\n"
        f"Query: {q}"
    )
    return _call_compound(prompt)
