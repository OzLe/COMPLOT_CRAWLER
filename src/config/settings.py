"""
Crawler settings and configuration constants.

This module centralizes all configurable parameters for the crawler,
making it easy to adjust behavior without modifying core logic.
"""

from dataclasses import dataclass


@dataclass
class CrawlerSettings:
    """Configuration settings for the Complot crawler."""

    # API Configuration
    api_base: str = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"

    # Concurrency settings
    max_concurrent: int = 20

    # Timeout and retry settings
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 2  # Base delay for exponential backoff

    # Checkpoint settings
    save_interval: int = 100  # Save progress every N records

    # Street discovery settings
    default_street_range: tuple[int, int] = (1, 2000)
    house_number_range: tuple[int, int] = (1, 500)

    # Test house numbers for street validation
    test_house_numbers: tuple[int, ...] = (1, 2, 3, 5, 10, 20, 50)


# Default settings instance
DEFAULT_SETTINGS = CrawlerSettings()
