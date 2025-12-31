"""
Tel Aviv Municipality GIS fetcher and parser.

Specialized fetcher for Tel Aviv's IView2 MapServer with parsing
for building permits and construction data.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

import aiohttp

from src.external.config import TLV_GIS_CONFIG, TLV_BUILDING_PERMITS_LAYER
from src.external.arcgis_fetcher import ArcGISFetcher
from src.models.gis import GISBuildingPermit, GISFeature, GISQueryResult

logger = logging.getLogger(__name__)


# Field names from the Tel Aviv building permits layer (IView2/MapServer/772)
# Based on actual layer schema inspection
TLV_PERMIT_FIELDS = [
    "oid_permit",           # Object ID
    "request_num",          # מספר בקשה
    "permission_date",      # תאריך היתר
    "permission_num",       # מספר היתר
    "expiry_date",          # תאריך תוקף היתר
    "open_request",         # תאריך פתיחת בקשה
    "building_num",         # קוד בניין
    "yechidot_diyur",       # יחידות דיור
    "building_stage",       # פעילות רישוי אחרונה בבניין
    "addresses",            # כתובות
    "sug_bakasha",          # סוג בקשה
    "tochen_bakasha",       # תוכן בקשה
    "sw_tama_38",           # תמא 38
    "sw_tama_38_chadash",   # תמא 38 חדש
    "sw_tama_38_tosefet",   # תמא 38 תוספת
    "finished",             # תאריך גמר
    "occupation",           # תאריך טופס אכלוס
    "tr_hathalat_bniya",    # תאריך התחלת בניה
    "request_stage",        # שלב בקשה
    "ms_tik_binyan",        # מס' תיק בניין
    "maslul_rishuy",        # מסלול רישוי
]


class TelAvivGISFetcher(ArcGISFetcher):
    """
    Fetcher specialized for Tel Aviv municipality GIS.

    Provides methods for querying building permits, construction sites,
    and other municipal GIS layers with proper parsing of Hebrew field names.
    """

    def __init__(self):
        """Initialize with Tel Aviv GIS configuration."""
        super().__init__(TLV_GIS_CONFIG)
        self.permits_layer_id = TLV_BUILDING_PERMITS_LAYER.layer_id

    def _parse_date(self, timestamp: Optional[int]) -> Optional[datetime]:
        """
        Parse ArcGIS timestamp to datetime.

        ArcGIS returns timestamps as milliseconds since epoch.
        """
        if timestamp is None:
            return None
        try:
            return datetime.fromtimestamp(timestamp / 1000)
        except (ValueError, OSError, TypeError):
            return None

    def _parse_permit(self, feature: GISFeature) -> GISBuildingPermit:
        """
        Parse a GIS feature into a building permit record.

        Args:
            feature: Raw GIS feature from query

        Returns:
            Parsed GISBuildingPermit
        """
        attrs = feature.attributes

        # Build TAMA-38 status string from multiple fields
        tama38_parts = []
        if attrs.get("sw_tama_38"):
            tama38_parts.append(attrs.get("sw_tama_38"))
        if attrs.get("sw_tama_38_chadash"):
            tama38_parts.append(f"חדש: {attrs.get('sw_tama_38_chadash')}")
        if attrs.get("sw_tama_38_tosefet"):
            tama38_parts.append(f"תוספת: {attrs.get('sw_tama_38_tosefet')}")

        return GISBuildingPermit(
            object_id=feature.object_id,
            request_number=attrs.get("request_num"),
            permit_number=attrs.get("permission_num"),
            building_code=attrs.get("building_num"),
            permit_date=self._parse_date(attrs.get("permission_date")),
            permit_expiry=self._parse_date(attrs.get("expiry_date")),
            request_open_date=self._parse_date(attrs.get("open_request")),
            address=attrs.get("addresses", ""),
            housing_units=attrs.get("yechidot_diyur"),
            permit_stage=attrs.get("building_stage", "") or attrs.get("request_stage", ""),
            tama38_type=attrs.get("sw_tama_38", ""),
            tama38_status=", ".join(tama38_parts) if tama38_parts else "",
            geometry=feature.geometry,
            centroid=self._extract_centroid(feature.geometry),
            source="telaviv",
            layer_id=self.permits_layer_id,
            fetched_at=feature.fetched_at,
            raw_attributes=attrs,
        )

    def _extract_centroid(self, geometry: Optional[Dict]) -> Optional[tuple]:
        """Extract centroid from polygon geometry."""
        if not geometry:
            return None

        rings = geometry.get("rings")
        if not rings or not rings[0]:
            return None

        # Calculate centroid from first ring
        ring = rings[0]
        x_sum = sum(pt[0] for pt in ring)
        y_sum = sum(pt[1] for pt in ring)
        n = len(ring)

        if n == 0:
            return None

        return (x_sum / n, y_sum / n)

    async def fetch_building_permits(
        self,
        session: aiohttp.ClientSession,
        where: str = "1=1",
        max_features: Optional[int] = None,
        out_fields: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None,
    ) -> List[GISBuildingPermit]:
        """
        Fetch building permits from Tel Aviv GIS.

        Args:
            session: aiohttp session
            where: SQL WHERE clause for filtering
            max_features: Maximum permits to fetch
            out_fields: Fields to return (None = default permit fields)
            progress_callback: Called with (fetched, total) counts

        Returns:
            List of GISBuildingPermit records
        """
        fields = out_fields or TLV_PERMIT_FIELDS

        result = await self.query_all_features(
            session,
            self.permits_layer_id,
            where=where,
            out_fields=fields,
            return_geometry=True,
            max_features=max_features,
            progress_callback=progress_callback,
        )

        if not result.success:
            logger.error(f"Failed to fetch permits: {result.error}")
            return []

        permits = [self._parse_permit(f) for f in result.features]
        logger.info(f"Fetched {len(permits)} building permits from Tel Aviv GIS")

        return permits

    async def fetch_permits_by_address(
        self,
        session: aiohttp.ClientSession,
        address: str,
    ) -> List[GISBuildingPermit]:
        """
        Fetch building permits matching an address.

        Args:
            session: aiohttp session
            address: Address to search for (partial match)

        Returns:
            List of matching GISBuildingPermit records
        """
        result = await self.query_by_address(
            session,
            self.permits_layer_id,
            address=address,
            address_field="addresses",
            out_fields=TLV_PERMIT_FIELDS,
        )

        if not result.success:
            logger.warning(f"Address search failed: {result.error}")
            return []

        return [self._parse_permit(f) for f in result.features]

    async def fetch_permits_by_street(
        self,
        session: aiohttp.ClientSession,
        street_name: str,
    ) -> List[GISBuildingPermit]:
        """
        Fetch all building permits on a street.

        Args:
            session: aiohttp session
            street_name: Street name to search for

        Returns:
            List of GISBuildingPermit records
        """
        # Escape single quotes
        safe_street = street_name.replace("'", "''")
        where = f"addresses LIKE '%{safe_street}%'"

        result = await self.query_all_features(
            session,
            self.permits_layer_id,
            where=where,
            out_fields=TLV_PERMIT_FIELDS,
        )

        if not result.success:
            logger.warning(f"Street search failed: {result.error}")
            return []

        return [self._parse_permit(f) for f in result.features]

    async def fetch_permits_by_date_range(
        self,
        session: aiohttp.ClientSession,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> List[GISBuildingPermit]:
        """
        Fetch building permits issued within a date range.

        Args:
            session: aiohttp session
            start_date: Start of date range
            end_date: End of date range (default: now)

        Returns:
            List of GISBuildingPermit records
        """
        if end_date is None:
            end_date = datetime.now()

        # Convert to epoch milliseconds for ArcGIS
        start_ms = int(start_date.timestamp() * 1000)
        end_ms = int(end_date.timestamp() * 1000)

        where = f"permission_date >= {start_ms} AND permission_date <= {end_ms}"

        result = await self.query_all_features(
            session,
            self.permits_layer_id,
            where=where,
            out_fields=TLV_PERMIT_FIELDS,
        )

        if not result.success:
            logger.warning(f"Date range search failed: {result.error}")
            return []

        return [self._parse_permit(f) for f in result.features]

    async def fetch_recent_permits(
        self,
        session: aiohttp.ClientSession,
        days: int = 30,
        max_features: Optional[int] = None,
    ) -> List[GISBuildingPermit]:
        """
        Fetch permits issued in the last N days.

        Args:
            session: aiohttp session
            days: Number of days to look back
            max_features: Maximum permits to return

        Returns:
            List of GISBuildingPermit records
        """
        from datetime import timedelta
        start_date = datetime.now() - timedelta(days=days)

        permits = await self.fetch_permits_by_date_range(
            session, start_date=start_date
        )

        if max_features and len(permits) > max_features:
            permits = permits[:max_features]

        return permits

    async def fetch_tama38_permits(
        self,
        session: aiohttp.ClientSession,
    ) -> List[GISBuildingPermit]:
        """
        Fetch all TAMA-38 (urban renewal) permits.

        Returns:
            List of GISBuildingPermit records with TAMA-38 classification
        """
        where = "tama38_type IS NOT NULL AND tama38_type <> ''"

        result = await self.query_all_features(
            session,
            self.permits_layer_id,
            where=where,
            out_fields=TLV_PERMIT_FIELDS,
        )

        if not result.success:
            logger.warning(f"TAMA-38 search failed: {result.error}")
            return []

        return [self._parse_permit(f) for f in result.features]

    async def get_layer_stats(
        self,
        session: aiohttp.ClientSession,
    ) -> Dict[str, Any]:
        """
        Get statistics about the building permits layer.

        Returns:
            Dict with count and date range info
        """
        # Get total count
        count_result = await self.query_layer(
            session,
            self.permits_layer_id,
            return_count_only=True,
        )

        stats = {
            "total_permits": count_result.total_count if count_result.success else 0,
            "source": "telaviv",
            "layer_id": self.permits_layer_id,
            "fetched_at": datetime.now().isoformat(),
        }

        return stats


async def fetch_tlv_building_permits(
    where: str = "1=1",
    max_features: Optional[int] = None,
) -> List[GISBuildingPermit]:
    """
    Standalone function to fetch Tel Aviv building permits.

    Args:
        where: SQL WHERE clause
        max_features: Maximum permits to fetch

    Returns:
        List of GISBuildingPermit records
    """
    fetcher = TelAvivGISFetcher()
    connector = fetcher.create_connector(fetcher.config.max_concurrent)

    async with aiohttp.ClientSession(connector=connector) as session:
        return await fetcher.fetch_building_permits(
            session,
            where=where,
            max_features=max_features,
        )


async def search_tlv_permits_by_address(address: str) -> List[GISBuildingPermit]:
    """
    Search Tel Aviv building permits by address.

    Args:
        address: Address to search for

    Returns:
        List of matching GISBuildingPermit records
    """
    fetcher = TelAvivGISFetcher()
    connector = fetcher.create_connector(fetcher.config.max_concurrent)

    async with aiohttp.ClientSession(connector=connector) as session:
        return await fetcher.fetch_permits_by_address(session, address)


# CLI for testing
if __name__ == "__main__":
    import sys

    async def main():
        fetcher = TelAvivGISFetcher()
        connector = fetcher.create_connector()

        async with aiohttp.ClientSession(connector=connector) as session:
            # Get stats first
            print("Fetching Tel Aviv GIS stats...")
            stats = await fetcher.get_layer_stats(session)
            print(f"Total permits in database: {stats['total_permits']}")

            # Fetch sample permits
            print("\nFetching sample permits (max 10)...")
            permits = await fetcher.fetch_building_permits(
                session, max_features=10
            )

            for permit in permits:
                print(f"\n--- Permit #{permit.permit_number or 'N/A'} ---")
                print(f"  Address: {permit.address}")
                print(f"  Date: {permit.permit_date}")
                print(f"  Housing Units: {permit.housing_units}")
                print(f"  Stage: {permit.permit_stage}")

            # Test address search if argument provided
            if len(sys.argv) > 1:
                address = sys.argv[1]
                print(f"\n\nSearching for address: {address}")
                results = await fetcher.fetch_permits_by_address(session, address)
                print(f"Found {len(results)} matching permits")

                for permit in results[:5]:
                    print(f"  - {permit.address}: {permit.permit_date}")

    asyncio.run(main())
