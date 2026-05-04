import uuid
from langchain_core.tools import tool




@tool("generate_uuid", description="Generate a random UUID v4.", return_direct=False)
def generate_uuid():
    """Generate a random UUID v4."""
    return {"uuid": str(uuid.uuid4())}
