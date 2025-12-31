"""
Configuration for external GIS data sources.

Contains configurations for municipal GIS systems and their ArcGIS REST endpoints.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ArcGISLayerConfig:
    """Configuration for an ArcGIS MapServer layer."""

    layer_id: int
    name: str
    name_he: str
    description: str = ""
    max_record_count: int = 2000
    geometry_type: str = "esriGeometryPolygon"

    # Field mappings for standardization
    field_mappings: dict = field(default_factory=dict)


@dataclass
class GISSourceConfig:
    """Configuration for a municipal GIS data source."""

    name: str                    # English name
    name_he: str                 # Hebrew name
    base_url: str                # Base URL for the MapServer
    city_code: int               # CBS city code (for matching with Complot data)
    spatial_reference: int = 2039  # EPSG code (2039 = Israel TM)

    # Available layers
    layers: dict = field(default_factory=dict)

    # Request configuration
    max_concurrent: int = 10
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0


# Tel Aviv GIS Layers
TLV_BUILDING_PERMITS_LAYER = ArcGISLayerConfig(
    layer_id=772,
    name="building_permits",
    name_he="בקשות והיתרי בניה",
    description="Building permit requests and approvals",
    max_record_count=2000,
    field_mappings={
        "request_num": "request_number",
        "permission_date": "permit_date",
        "permission_num": "permit_number",
        "expiry_date": "permit_expiry",
        "open_request": "request_open_date",
        "building_num": "building_code",
        "yechidot_diyur": "housing_units",
        "building_stage": "permit_stage",
        "addresses": "address",
    }
)

TLV_CONSTRUCTION_SITES_LAYER = ArcGISLayerConfig(
    layer_id=499,
    name="construction_sites",
    name_he="אתרי בניה",
    description="Active construction sites",
    max_record_count=2000,
)

TLV_BUILDINGS_LAYER = ArcGISLayerConfig(
    layer_id=513,
    name="buildings",
    name_he="מבנים",
    description="Building footprints",
    max_record_count=2000,
)

TLV_CITY_PLANS_LAYER = ArcGISLayerConfig(
    layer_id=528,
    name="city_plans",
    name_he="תוכניות בניין עיר",
    description="City building plans",
    max_record_count=2000,
)

TLV_DANGEROUS_BUILDINGS_LAYER = ArcGISLayerConfig(
    layer_id=591,
    name="dangerous_buildings",
    name_he="מבנים מסוכנים",
    description="Dangerous buildings registry",
    max_record_count=2000,
)

TLV_LICENSING_ZONES_LAYER = ArcGISLayerConfig(
    layer_id=622,
    name="licensing_zones",
    name_he="אזורי רישוי בניה",
    description="Building licensing zones",
    max_record_count=2000,
)


# Tel Aviv GIS Configuration
TLV_GIS_CONFIG = GISSourceConfig(
    name="telaviv",
    name_he="תל אביב-יפו",
    base_url="https://gisn.tel-aviv.gov.il/arcgis/rest/services/IView2/MapServer",
    city_code=5000,  # Tel Aviv CBS code
    spatial_reference=2039,
    layers={
        "building_permits": TLV_BUILDING_PERMITS_LAYER,
        "construction_sites": TLV_CONSTRUCTION_SITES_LAYER,
        "buildings": TLV_BUILDINGS_LAYER,
        "city_plans": TLV_CITY_PLANS_LAYER,
        "dangerous_buildings": TLV_DANGEROUS_BUILDINGS_LAYER,
        "licensing_zones": TLV_LICENSING_ZONES_LAYER,
    },
    max_concurrent=10,
    request_timeout=30,
)


# Registry of all available GIS sources
ARCGIS_LAYERS = {
    "telaviv": TLV_GIS_CONFIG,
}


def get_gis_config(city: str) -> Optional[GISSourceConfig]:
    """
    Get GIS configuration for a city.

    Args:
        city: City name (English)

    Returns:
        GISSourceConfig or None if not available
    """
    return ARCGIS_LAYERS.get(city.lower())


def list_gis_sources() -> list[dict]:
    """List all available GIS data sources."""
    return [
        {
            "name": config.name,
            "name_he": config.name_he,
            "city_code": config.city_code,
            "layers": list(config.layers.keys()),
            "base_url": config.base_url,
        }
        for config in ARCGIS_LAYERS.values()
    ]


if __name__ == "__main__":
    print("Available GIS Sources:")
    print("-" * 60)
    for source in list_gis_sources():
        print(f"  {source['name']:15} | {source['name_he']:15} | Layers: {', '.join(source['layers'])}")
