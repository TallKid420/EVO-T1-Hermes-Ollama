from datetime import datetime
from langchain_core.tools import tool




@tool("get_time", description="get_time tool", return_direct=False)
def get_time(timezone=None):
    timezone = timezone or "EDT"
    try:
        import pytz

        time = datetime.now(pytz.timezone(timezone)).isoformat(timespec="seconds")
    except ModuleNotFoundError:
        return {"error": "pytz is not installed"}
    except pytz.UnknownTimeZoneError:
        return {"error": f"Unknown timezone: {timezone}"}
    return {"timezone": timezone, "time": time}
