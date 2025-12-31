"""Configuration module for Complot Crawler."""

from src.config.settings import CrawlerSettings, DEFAULT_SETTINGS
from src.config.cities import CityConfig, CITIES, get_city_config, list_cities, parse_url_config

__all__ = [
    "CrawlerSettings",
    "DEFAULT_SETTINGS",
    "CityConfig",
    "CITIES",
    "get_city_config",
    "list_cities",
    "parse_url_config",
]
