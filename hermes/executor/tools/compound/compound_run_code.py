from hermes.executor.tools.compound.compound_search import _call_compound
from langchain_core.tools import tool




@tool("compound_run_code", description="Ask groq/compound to use code interpreter for a computation task.", return_direct=False)
def compound_run_code(task: str, language: str = "python") -> dict:
    """Ask groq/compound to use code interpreter for a computation task."""
    t = str(task).strip()
    if not t:
        return {"error": "task is required"}
    lang = str(language or "python").strip().lower()
    prompt = (
        "Use the code interpreter tool to complete this task. "
        "Show the final answer and a brief note of what code was executed.\n\n"
        f"Language: {lang}\n"
        f"Task: {t}"
    )
    return _call_compound(prompt)
