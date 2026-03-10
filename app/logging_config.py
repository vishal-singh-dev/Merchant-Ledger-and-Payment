import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from pythonjsonlogger import jsonlogger


def configure_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_file_path: str = "logs/app.log",
    log_file_max_bytes: int = 5_242_880,
    log_file_backup_count: int = 5,
) -> None:
    stream_handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s")
    stream_handler.setFormatter(formatter)
    handlers: list[logging.Handler] = [stream_handler]

    if log_to_file:
        file_path = Path(log_file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=log_file_max_bytes,
            backupCount=log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)
