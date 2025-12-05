import logging
import sys
from typing import Optional

def setup_logger(name: str = "eks_addon_installer", level: int = logging.INFO) -> logging.Logger:
    """Set up and return a logger with console handler."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent adding multiple handlers if logger already exists
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

def log_section(logger: logging.Logger, title: str):
    """Log a section header for better readability."""
    logger.info("=" * 60)
    logger.info(f"{title}")
    logger.info("=" * 60)