"""
GIS-related data models.

Contains dataclasses for building data from external GIS sources
(ArcGIS REST services from municipal portals).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class GISBuildingPermit:
    """
    Building permit record from municipal GIS.

    Represents detailed permit information from ArcGIS MapServer layers,
    particularly Tel Aviv's IView2/MapServer/772 (בקשות והיתרי בניה).
    """

    # Core identifiers
    object_id: int
    request_number: Optional[int] = None
    permit_number: Optional[int] = None
    building_code: Optional[int] = None

    # Dates
    permit_date: Optional[datetime] = None
    permit_expiry: Optional[datetime] = None
    request_open_date: Optional[datetime] = None

    # Address info
    address: str = ""
    addresses_list: list = field(default_factory=list)

    # Building info
    housing_units: Optional[int] = None
    permit_stage: str = ""

    # TAMA-38 related (urban renewal)
    tama38_type: str = ""
    tama38_status: str = ""

    # Geometry
    geometry: Optional[dict] = None
    centroid: Optional[tuple] = None

    # Metadata
    source: str = ""
    layer_id: int = 0
    fetched_at: str = ""
    raw_attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "object_id": self.object_id,
            "request_number": self.request_number,
            "permit_number": self.permit_number,
            "building_code": self.building_code,
            "permit_date": self.permit_date.isoformat() if self.permit_date else None,
            "permit_expiry": self.permit_expiry.isoformat() if self.permit_expiry else None,
            "request_open_date": self.request_open_date.isoformat() if self.request_open_date else None,
            "address": self.address,
            "addresses_list": self.addresses_list,
            "housing_units": self.housing_units,
            "permit_stage": self.permit_stage,
            "tama38_type": self.tama38_type,
            "tama38_status": self.tama38_status,
            "geometry": self.geometry,
            "centroid": self.centroid,
            "source": self.source,
            "layer_id": self.layer_id,
            "fetched_at": self.fetched_at,
        }


@dataclass
class GISFeature:
    """
    Generic GIS feature from ArcGIS MapServer.

    Used for layers that don't have specialized models.
    """

    object_id: int
    attributes: dict = field(default_factory=dict)
    geometry: Optional[dict] = None
    geometry_type: str = ""
    spatial_reference: int = 2039

    # Metadata
    layer_id: int = 0
    layer_name: str = ""
    source: str = ""
    fetched_at: str = ""

    def get_attribute(self, name: str, default: Any = None) -> Any:
        """Get attribute value by name."""
        return self.attributes.get(name, default)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "object_id": self.object_id,
            "attributes": self.attributes,
            "geometry": self.geometry,
            "geometry_type": self.geometry_type,
            "spatial_reference": self.spatial_reference,
            "layer_id": self.layer_id,
            "layer_name": self.layer_name,
            "source": self.source,
            "fetched_at": self.fetched_at,
        }


@dataclass
class GISQueryResult:
    """
    Result of a GIS query operation.

    Contains features and metadata about the query.
    """

    features: list = field(default_factory=list)
    total_count: int = 0
    exceeded_limit: bool = False

    # Query metadata
    layer_id: int = 0
    layer_name: str = ""
    source: str = ""
    where_clause: str = ""
    out_fields: list = field(default_factory=list)

    # Pagination
    offset: int = 0
    result_count: int = 0

    # Errors
    error: str = ""
    success: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_count": self.total_count,
            "result_count": self.result_count,
            "exceeded_limit": self.exceeded_limit,
            "layer_id": self.layer_id,
            "layer_name": self.layer_name,
            "source": self.source,
            "where_clause": self.where_clause,
            "offset": self.offset,
            "success": self.success,
            "error": self.error,
            "features": [f.to_dict() if hasattr(f, 'to_dict') else f for f in self.features],
        }


@dataclass
class EnrichedBuildingRecord:
    """
    Building record enriched with data from external GIS sources.

    Combines Complot basic record with additional details from
    municipal GIS systems.
    """

    # Original Complot data
    tik_number: str
    address: str = ""
    gush: str = ""
    helka: str = ""
    street_code: int = 0
    street_name: str = ""

    # Enriched from GIS
    permit_number: Optional[int] = None
    permit_date: Optional[datetime] = None
    permit_expiry: Optional[datetime] = None
    housing_units: Optional[int] = None
    permit_stage: str = ""
    building_code: Optional[int] = None

    # GIS geometry (if matched)
    geometry: Optional[dict] = None
    centroid: Optional[tuple] = None

    # Match metadata
    gis_source: str = ""
    gis_object_id: Optional[int] = None
    match_method: str = ""  # "address", "gush_helka", "geometry"
    match_confidence: float = 0.0

    # Status
    enriched: bool = False
    enriched_at: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "tik_number": self.tik_number,
            "address": self.address,
            "gush": self.gush,
            "helka": self.helka,
            "street_code": self.street_code,
            "street_name": self.street_name,
            "permit_number": self.permit_number,
            "permit_date": self.permit_date.isoformat() if self.permit_date else None,
            "permit_expiry": self.permit_expiry.isoformat() if self.permit_expiry else None,
            "housing_units": self.housing_units,
            "permit_stage": self.permit_stage,
            "building_code": self.building_code,
            "geometry": self.geometry,
            "centroid": self.centroid,
            "gis_source": self.gis_source,
            "gis_object_id": self.gis_object_id,
            "match_method": self.match_method,
            "match_confidence": self.match_confidence,
            "enriched": self.enriched,
            "enriched_at": self.enriched_at,
        }
