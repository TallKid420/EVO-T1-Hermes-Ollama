from hermes.executor.tools.compound.compound_search import _call_compound
from langchain_core.tools import tool




@tool("compound_visit_website", description="Ask groq/compound to visit a website and return extracted information.", return_direct=False)
def compound_visit_website(url: str, instruction: str = "Summarize the key points.") -> dict:
    """Ask groq/compound to visit a website and return extracted information."""
    u = str(url).strip()
    if not u:
        return {"error": "url is required"}
    prompt = (
        "Visit this website and follow the instruction below. "
        "Include important factual details and cite the page URL in your response.\n\n"
        f"URL: {u}\n"
        f"Instruction: {instruction}"
    )
    return _call_compound(prompt)
