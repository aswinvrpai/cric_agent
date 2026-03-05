# src/logger/logger.py

from datetime import datetime
import logging
from pathlib import Path
from from_root import from_root

# Logs directory
logs_root = Path(from_root("logs"))
date_dir = logs_root / datetime.now().strftime("%Y-%m-%d")
date_dir.mkdir(parents=True, exist_ok=True)
log_file = date_dir / f"{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.log"

"""
Creates and returns a logger with file + console handlers
"""
def setup_logger(name: str, log_file: Path = log_file) -> logging.Logger:

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    logger.propagate = False  # THIS FIXES DUPLICATION

    # Prevent duplicate logs
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
