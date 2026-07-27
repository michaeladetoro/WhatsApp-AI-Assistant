"""
Structured logging setup for the WhatsApp RAG Bot.
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"


def setup_logger(name: str = "RAGBot", force_root: bool = False) -> logging.Logger:
    """
    Set up a logger with console and optional file output.
    Set ENABLE_FILE_LOGGING=true in .env to enable daily log files.
    """
    target = logging.getLogger() if force_root else logging.getLogger(name)
    target.setLevel(logging.INFO)

    # Avoid adding duplicate handlers on reload
    if target.hasHandlers():
        target.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(LOG_FORMAT))
    target.addHandler(console)

    # File handler (optional)
    if os.getenv("ENABLE_FILE_LOGGING", "false").lower() == "true":
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        file_handler = logging.FileHandler(log_dir / f"wabot_{today}.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        target.addHandler(file_handler)

    target.propagate = False
    return target


# Module-level logger for internal use
logger = logging.getLogger("RAGBot")
