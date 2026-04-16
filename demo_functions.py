from executor import EXECUTOR, TOOLS as LOCAL_TOOLS
import json

# Canonicalized tool schema keeps request bytes stable for better cache reuse.
_STATIC_TOOLS = json.loads(json.dumps(LOCAL_TOOLS, sort_keys=True, separators=(",", ":")))

print("Tools:", json.dumps(_STATIC_TOOLS, indent=2))