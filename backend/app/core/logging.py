"""
Centralised logging configuration.

Every major processing stage (validation, OCR, extraction, financial
validation, persistence) logs through the logger returned by
``get_logger(__name__)`` so failures during evaluation can be diagnosed
from the console / platform log stream without needing a debugger.
"""
import logging
import sys

from app.core.config import get_settings

_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    # Avoid duplicate handlers on reload
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet down noisy third-party loggers a little
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
