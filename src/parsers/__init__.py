"""HTML parsers for Complot API responses."""

from src.parsers.base import BaseParser
from src.parsers.building_parser import BuildingDetailParser
from src.parsers.request_parser import RequestDetailParser
from src.parsers.search_parser import SearchResultParser

__all__ = [
    "BaseParser",
    "BuildingDetailParser",
    "RequestDetailParser",
    "SearchResultParser",
]
