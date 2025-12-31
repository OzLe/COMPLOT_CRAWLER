"""
External data sources module for enriching building records.

This module provides fetchers and parsers for external GIS and open data sources
that can supplement the Complot building records with additional details.
"""

from src.external.config import (
    GISSourceConfig,
    TLV_GIS_CONFIG,
    ARCGIS_LAYERS,
    get_gis_config,
    list_gis_sources,
)
from src.external.arcgis_fetcher import ArcGISFetcher, fetch_gis_features
from src.external.tlv_gis import (
    TelAvivGISFetcher,
    fetch_tlv_building_permits,
    search_tlv_permits_by_address,
)
from src.external.enricher import BuildingEnricher, enrich_building_records

__all__ = [
    # Config
    "GISSourceConfig",
    "TLV_GIS_CONFIG",
    "ARCGIS_LAYERS",
    "get_gis_config",
    "list_gis_sources",
    # Fetchers
    "ArcGISFetcher",
    "fetch_gis_features",
    "TelAvivGISFetcher",
    "fetch_tlv_building_permits",
    "search_tlv_permits_by_address",
    # Enrichment
    "BuildingEnricher",
    "enrich_building_records",
]
