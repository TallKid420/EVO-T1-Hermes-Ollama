import os


def read_logs(
    log_path: str = "hermes.log",
    lines_n: int = 100,
    filter_: str = None,
    level: str = None,
) -> dict:
    if not os.path.exists(log_path):
        return {"error": f"Log file not found: {log_path}"}

    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if filter_:
        lines = [l for l in lines if filter_.lower() in l.lower()]
    if level:
        lines = [l for l in lines if level.upper() in l]

    return {"lines": [l.rstrip() for l in lines[-lines_n:]]}