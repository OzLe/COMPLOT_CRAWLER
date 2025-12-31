"""
Logging configuration for Complot Crawler.

Provides a standardized logging setup with both console and file output.
"""

import logging
import sys
from pathlib import Path
from typing import Optional


# Default logger name
LOGGER_NAME = "complot_crawler"

# Cached logger instance
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get the crawler logger instance."""
    global _logger
    if _logger is None:
        _logger = logging.getLogger(LOGGER_NAME)
    return _logger


def setup_logging(output_dir: Path, verbose: bool = False) -> logging.Logger:
    """
    Configure logging with console and file handlers.

    Args:
        output_dir: Directory where the log file will be created
        verbose: If True, set console log level to DEBUG

    Returns:
        Configured logger instance
    """
    logger = get_logger()
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter with timestamp
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # File handler
    log_file = output_dir / "crawler.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # Always log debug to file
    file_handler.setFormatter(formatter)

    # Configure logger
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # Remove existing handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")

    return logger
