import hashlib
from langchain_core.tools import tool




@tool("hash_text", description="Hash a string using md5, sha1, or sha256.", return_direct=False)
def hash_text(text: str, algorithm: str = "sha256"):
    """Hash a string using md5, sha1, or sha256."""
    algo = algorithm.lower().replace("-", "")
    supported = {"md5", "sha1", "sha256"}
    if algo not in supported:
        return {"error": f"Unsupported algorithm '{algorithm}'. Choose from: {', '.join(supported)}"}
    h = hashlib.new(algo, text.encode()).hexdigest()
    return {"algorithm": algo, "hash": h}
