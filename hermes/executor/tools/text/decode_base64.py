import base64
from langchain_core.tools import tool




@tool("decode_base64", description="Decode a Base64 string back to UTF-8 text.", return_direct=False)
def decode_base64(encoded: str):
    """Decode a Base64 string back to UTF-8 text."""
    try:
        decoded = base64.b64decode(encoded.encode()).decode()
        return {"encoded": encoded, "decoded": decoded}
    except Exception as e:
        return {"error": str(e)}
