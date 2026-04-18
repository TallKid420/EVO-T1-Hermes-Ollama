import logging
from pathlib import Path

from rich.logging import RichHandler


def configure_terminal_logging(log_file: str = "hermes.log", level: int = logging.INFO) -> None:
    """Configure Rich terminal logs plus plain file logs for the daemon."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    rich_handler = RichHandler(rich_tracebacks=True, show_time=True, show_path=False)
    rich_handler.setLevel(level)
    rich_handler.setFormatter(logging.Formatter("%(message)s"))

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )

    root.addHandler(rich_handler)
    root.addHandler(file_handler)
