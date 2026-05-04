import os
import time
from langchain_core.tools import tool




@tool("_call_compound", description="Send a prompt to groq/compound and return structured output.", return_direct=False)
def _call_compound(prompt: str) -> dict:
    """Send a prompt to groq/compound and return structured output."""
    try:
        from groq import Groq  # noqa: PLC0415

        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key:
            return {"error": "GROQ_API_KEY not set"}

        compound_model = os.environ.get("OPERATOR_COMPOUND_MODEL", "groq/compound")
        timeout_seconds = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "30"))
        max_retries = max(0, int(os.environ.get("GROQ_MAX_RETRIES", "2")))
        client = Groq(api_key=api_key)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                resp = client.chat.completions.create(
                    model=compound_model,
                    messages=[{"role": "user", "content": str(prompt).strip()}],
                    temperature=0,
                    timeout=timeout_seconds,
                )
                break
            except Exception as e:
                last_error = e
                if attempt >= max_retries:
                    return {"error": str(e)}
                __import__("time").sleep(min(2 ** attempt, 4))

        if 'resp' not in locals():
            return {"error": str(last_error) if last_error else "compound request failed"}

        msg = resp.choices[0].message
        content = (msg.content or "").strip()

        executed_tools = []
        for t in getattr(msg, "executed_tools", None) or []:
            tool_type = str(getattr(t, "type", "") or "").strip()
            if tool_type:
                executed_tools.append(tool_type)

        return {
            "result": content,
            "model": compound_model,
            "executed_tools": executed_tools,
        }
    except Exception as e:
        return {"error": str(e)}




@tool("compound_search", description="General-purpose route to groq/compound for live web or code tasks.", return_direct=False)
def compound_search(query: str, context: str = "") -> dict:
    """General-purpose route to groq/compound for live web or code tasks."""
    prompt = str(query).strip()
    if context:
        prompt = f"{context.strip()}\n\n{prompt}"
    return _call_compound(prompt)
