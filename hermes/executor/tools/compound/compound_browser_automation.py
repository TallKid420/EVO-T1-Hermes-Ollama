from hermes.executor.tools.compound.compound_search import _call_compound
from langchain_core.tools import tool




@tool("compound_browser_automation", description="Ask groq/compound to use browser automation for a multi-step browser task.", return_direct=False)
def compound_browser_automation(task: str) -> dict:
    """Ask groq/compound to use browser automation for a multi-step browser task."""
    t = str(task).strip()
    if not t:
        return {"error": "task is required"}
    prompt = (
        "Use browser automation to complete this browser task. "
        "Return the final outcome and key steps performed.\n\n"
        f"Task: {t}"
    )
    return _call_compound(prompt)
