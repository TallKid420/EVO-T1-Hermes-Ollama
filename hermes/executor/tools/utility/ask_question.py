from langchain_core.tools import tool
@tool("ask_question", description="Prompt the local user for follow-up input and return their answer.", return_direct=False)
def ask_question(question: str):
    """Prompt the local user for follow-up input and return their answer."""
    try:
        answer = input(f"Hermes follow-up: {question}\n> ").strip()
        return {"question": question, "answer": answer}
    except Exception as e:
        return {"error": str(e)}
