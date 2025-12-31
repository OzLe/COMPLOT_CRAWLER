"""Async HTTP fetchers for Complot API."""

from src.fetchers.base import build_url, BaseFetcher
from src.fetchers.street_fetcher import StreetFetcher, async_test_street, async_discover_range
from src.fetchers.record_fetcher import RecordFetcher, async_fetch_records_for_street
from src.fetchers.building_fetcher import BuildingFetcher, async_fetch_building_detail
from src.fetchers.request_fetcher import RequestFetcher, async_fetch_request_detail

__all__ = [
    # Base
    "build_url",
    "BaseFetcher",
    # Street discovery
    "StreetFetcher",
    "async_test_street",
    "async_discover_range",
    # Record fetching
    "RecordFetcher",
    "async_fetch_records_for_street",
    # Building details
    "BuildingFetcher",
    "async_fetch_building_detail",
    # Request details
    "RequestFetcher",
    "async_fetch_request_detail",
]
