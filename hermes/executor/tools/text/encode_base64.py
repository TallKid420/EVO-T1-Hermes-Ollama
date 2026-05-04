import base64
from langchain_core.tools import tool




@tool("encode_base64", description="Encode a UTF-8 string to Base64.", return_direct=False)
def encode_base64(text: str):
    """Encode a UTF-8 string to Base64."""
    encoded = base64.b64encode(text.encode()).decode()
    return {"original": text, "encoded": encoded}
