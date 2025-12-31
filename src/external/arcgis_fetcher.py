"""
Generic ArcGIS REST API fetcher.

Provides async HTTP operations for querying ArcGIS MapServer and FeatureServer
endpoints commonly used by Israeli municipal GIS systems.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

import aiohttp

from src.external.config import GISSourceConfig, ArcGISLayerConfig
from src.models.gis import GISFeature, GISQueryResult

logger = logging.getLogger(__name__)


class ArcGISFetcher:
    """
    Async fetcher for ArcGIS REST API endpoints.

    Supports querying MapServer layers with pagination, field selection,
    spatial queries, and attribute filtering.
    """

    def __init__(self, config: GISSourceConfig):
        """
        Initialize ArcGIS fetcher.

        Args:
            config: GIS source configuration
        """
        self.config = config
        self.timeout = aiohttp.ClientTimeout(total=config.request_timeout)

    def _build_query_url(self, layer_id: int) -> str:
        """Build query URL for a layer."""
        return f"{self.config.base_url}/{layer_id}/query"

    def _build_layer_info_url(self, layer_id: int) -> str:
        """Build info URL for a layer."""
        return f"{self.config.base_url}/{layer_id}"

    def get_headers(self) -> Dict[str, str]:
        """Get default HTTP headers."""
        return {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }

    async def fetch_layer_info(
        self,
        session: aiohttp.ClientSession,
        layer_id: int
    ) -> Optional[Dict]:
        """
        Fetch metadata about a layer.

        Args:
            session: aiohttp session
            layer_id: Layer ID to query

        Returns:
            Layer metadata dict or None on error
        """
        url = self._build_layer_info_url(layer_id)
        params = {"f": "json"}

        try:
            async with session.get(
                url,
                params=params,
                headers=self.get_headers(),
                timeout=self.timeout
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"Layer info request failed: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"Error fetching layer info: {e}")
            return None

    async def query_layer(
        self,
        session: aiohttp.ClientSession,
        layer_id: int,
        where: str = "1=1",
        out_fields: Union[str, List[str]] = "*",
        return_geometry: bool = True,
        geometry_type: str = "esriGeometryEnvelope",
        geometry: Optional[Dict] = None,
        spatial_rel: str = "esriSpatialRelIntersects",
        result_offset: int = 0,
        result_record_count: Optional[int] = None,
        order_by_fields: Optional[str] = None,
        return_count_only: bool = False,
        out_sr: Optional[int] = None,
    ) -> GISQueryResult:
        """
        Query a MapServer layer.

        Args:
            session: aiohttp session
            layer_id: Layer ID to query
            where: SQL WHERE clause
            out_fields: Fields to return (* for all)
            return_geometry: Whether to return geometry
            geometry_type: Geometry type for spatial queries
            geometry: Geometry dict for spatial queries
            spatial_rel: Spatial relationship for queries
            result_offset: Pagination offset
            result_record_count: Max records to return
            order_by_fields: Field(s) to order by
            return_count_only: Only return count, not features
            out_sr: Output spatial reference

        Returns:
            GISQueryResult with features and metadata
        """
        url = self._build_query_url(layer_id)

        # Build params
        if isinstance(out_fields, list):
            out_fields = ",".join(out_fields)

        params = {
            "where": where,
            "outFields": out_fields,
            "returnGeometry": str(return_geometry).lower(),
            "f": "json",
        }

        if result_offset > 0:
            params["resultOffset"] = result_offset

        if result_record_count:
            params["resultRecordCount"] = result_record_count

        if order_by_fields:
            params["orderByFields"] = order_by_fields

        if return_count_only:
            params["returnCountOnly"] = "true"

        if out_sr:
            params["outSR"] = out_sr

        if geometry:
            params["geometry"] = str(geometry)
            params["geometryType"] = geometry_type
            params["spatialRel"] = spatial_rel

        result = GISQueryResult(
            layer_id=layer_id,
            source=self.config.name,
            where_clause=where,
            offset=result_offset,
        )

        try:
            async with session.get(
                url,
                params=params,
                headers=self.get_headers(),
                timeout=self.timeout
            ) as resp:
                if resp.status != 200:
                    result.success = False
                    result.error = f"HTTP {resp.status}"
                    return result

                data = await resp.json()

                # Check for ArcGIS error
                if "error" in data:
                    result.success = False
                    result.error = data["error"].get("message", "Unknown error")
                    return result

                # Handle count-only response
                if return_count_only:
                    result.total_count = data.get("count", 0)
                    return result

                # Parse features
                features = data.get("features", [])
                result.result_count = len(features)
                result.exceeded_limit = data.get("exceededTransferLimit", False)

                for feature_data in features:
                    attrs = feature_data.get("attributes", {})
                    geom = feature_data.get("geometry")

                    # Try common OID field names
                    object_id = (
                        attrs.get("OBJECTID") or
                        attrs.get("objectid") or
                        attrs.get("OID") or
                        attrs.get("oid") or
                        attrs.get("oid_permit") or  # Tel Aviv uses this
                        attrs.get("FID") or
                        0
                    )

                    feature = GISFeature(
                        object_id=object_id,
                        attributes=attrs,
                        geometry=geom,
                        layer_id=layer_id,
                        source=self.config.name,
                        fetched_at=datetime.now().isoformat(),
                    )
                    result.features.append(feature)

                return result

        except asyncio.TimeoutError:
            result.success = False
            result.error = "Request timeout"
            return result
        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"Error querying layer {layer_id}: {e}")
            return result

    async def query_all_features(
        self,
        session: aiohttp.ClientSession,
        layer_id: int,
        where: str = "1=1",
        out_fields: Union[str, List[str]] = "*",
        return_geometry: bool = True,
        batch_size: int = 2000,
        max_features: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> GISQueryResult:
        """
        Query all features from a layer with automatic pagination.

        Args:
            session: aiohttp session
            layer_id: Layer ID to query
            where: SQL WHERE clause
            out_fields: Fields to return
            return_geometry: Whether to return geometry
            batch_size: Records per request
            max_features: Maximum total features to fetch
            progress_callback: Called with (fetched_count, total_count)

        Returns:
            GISQueryResult with all features
        """
        # First get total count
        count_result = await self.query_layer(
            session, layer_id, where=where, return_count_only=True
        )

        if not count_result.success:
            return count_result

        total_count = count_result.total_count
        if max_features:
            total_count = min(total_count, max_features)

        logger.info(f"Fetching {total_count} features from layer {layer_id}")

        all_features = []
        offset = 0

        while offset < total_count:
            # Adjust batch size if we're close to max_features
            remaining = total_count - offset
            current_batch_size = min(batch_size, remaining)

            batch_result = await self.query_layer(
                session,
                layer_id,
                where=where,
                out_fields=out_fields,
                return_geometry=return_geometry,
                result_offset=offset,
                result_record_count=current_batch_size,
            )

            if not batch_result.success:
                logger.warning(f"Batch at offset {offset} failed: {batch_result.error}")
                break

            all_features.extend(batch_result.features)
            offset += len(batch_result.features)

            if progress_callback:
                progress_callback(len(all_features), total_count)

            # Stop if we got fewer than requested or reached our limit
            if len(batch_result.features) < current_batch_size:
                break

            if max_features and len(all_features) >= max_features:
                break

            # Small delay to be nice to the server
            await asyncio.sleep(0.1)

        return GISQueryResult(
            features=all_features,
            total_count=total_count,
            result_count=len(all_features),
            exceeded_limit=len(all_features) < total_count,
            layer_id=layer_id,
            source=self.config.name,
            where_clause=where,
            success=True,
        )

    async def query_by_address(
        self,
        session: aiohttp.ClientSession,
        layer_id: int,
        address: str,
        address_field: str = "addresses",
        out_fields: Union[str, List[str]] = "*",
    ) -> GISQueryResult:
        """
        Query features by address match.

        Args:
            session: aiohttp session
            layer_id: Layer ID to query
            address: Address to search for
            address_field: Field containing address
            out_fields: Fields to return

        Returns:
            GISQueryResult with matching features
        """
        # Escape single quotes in address
        safe_address = address.replace("'", "''")
        where = f"{address_field} LIKE '%{safe_address}%'"

        return await self.query_layer(
            session, layer_id, where=where, out_fields=out_fields
        )

    async def query_by_bbox(
        self,
        session: aiohttp.ClientSession,
        layer_id: int,
        xmin: float,
        ymin: float,
        xmax: float,
        ymax: float,
        spatial_reference: int = 2039,
        out_fields: Union[str, List[str]] = "*",
    ) -> GISQueryResult:
        """
        Query features within a bounding box.

        Args:
            session: aiohttp session
            layer_id: Layer ID to query
            xmin, ymin, xmax, ymax: Bounding box coordinates
            spatial_reference: Spatial reference of coordinates
            out_fields: Fields to return

        Returns:
            GISQueryResult with features in bbox
        """
        geometry = {
            "xmin": xmin,
            "ymin": ymin,
            "xmax": xmax,
            "ymax": ymax,
            "spatialReference": {"wkid": spatial_reference}
        }

        return await self.query_layer(
            session,
            layer_id,
            geometry=geometry,
            geometry_type="esriGeometryEnvelope",
            spatial_rel="esriSpatialRelIntersects",
            out_fields=out_fields,
        )

    @staticmethod
    def create_connector(limit: int = 10) -> aiohttp.TCPConnector:
        """Create a TCP connector with appropriate limits."""
        return aiohttp.TCPConnector(limit=limit)

    @staticmethod
    def create_semaphore(limit: int = 10) -> asyncio.Semaphore:
        """Create a semaphore for concurrency control."""
        return asyncio.Semaphore(limit)


async def fetch_gis_features(
    config: GISSourceConfig,
    layer_id: int,
    where: str = "1=1",
    out_fields: str = "*",
    max_features: Optional[int] = None,
) -> GISQueryResult:
    """
    Standalone function to fetch GIS features.

    Args:
        config: GIS source configuration
        layer_id: Layer ID to query
        where: SQL WHERE clause
        out_fields: Fields to return
        max_features: Maximum features to fetch

    Returns:
        GISQueryResult with features
    """
    fetcher = ArcGISFetcher(config)
    connector = fetcher.create_connector(config.max_concurrent)

    async with aiohttp.ClientSession(connector=connector) as session:
        return await fetcher.query_all_features(
            session,
            layer_id,
            where=where,
            out_fields=out_fields,
            max_features=max_features,
        )
