"""
Structured logging configuration for offshore risk detection.
Ensures PII redaction and proper log levels.
"""
import logging
import os
import sys
from typing import Optional


def redact_account_number(account: Optional[str]) -> str:
    """Redact account number, showing only last 4 digits."""
    if not account or not isinstance(account, str):
        return "****"
    account_str = str(account).strip()
    if len(account_str) <= 4:
        return "****"
    return f"****{account_str[-4:]}"


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger instance.
    
    Args:
        name: Logger name (usually __name__)
        level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to env LOG_LEVEL or INFO.
    
    Returns:
        Configured logger instance
    """
    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Avoid duplicate handlers
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level.upper()))
        
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
