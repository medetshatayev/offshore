"""
Structured logging configuration for offshore risk detection.
Provides consistent logging setup across the application.
"""
import logging
import os
import sys
from typing import Optional


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger instance with structured formatting.

    Args:
        name: Logger name (typically __name__ from calling module)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to LOG_LEVEL environment variable or INFO.

    Returns:
        Configured logger instance with StreamHandler
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO")

    new_logger = logging.getLogger(name)
    new_logger.setLevel(getattr(logging, log_level.upper()))

    # Avoid duplicate handlers if logger already configured
    if not new_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level.upper()))

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        new_logger.addHandler(handler)

    return new_logger
