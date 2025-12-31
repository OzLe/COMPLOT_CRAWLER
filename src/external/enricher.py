"""
Building record enrichment module.

Enriches Complot building records with data from external GIS sources.
Can be run standalone or integrated into the main crawler workflow.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import aiohttp
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.console import Console

from src.external.tlv_gis import TelAvivGISFetcher
from src.models.gis import GISBuildingPermit, EnrichedBuildingRecord

logger = logging.getLogger(__name__)
console = Console()


class BuildingEnricher:
    """
    Enriches building records from Complot with GIS data.

    Matches records by address and enriches with permit details,
    housing units, permit stages, and geometry.
    """

    def __init__(self, gis_source: str = "telaviv"):
        """
        Initialize enricher.

        Args:
            gis_source: GIS source to use for enrichment
        """
        self.gis_source = gis_source

        if gis_source == "telaviv":
            self.fetcher = TelAvivGISFetcher()
        else:
            raise ValueError(f"Unknown GIS source: {gis_source}")

        self.permits_cache: Dict[str, List[GISBuildingPermit]] = {}
        self.stats = {
            "total_records": 0,
            "enriched": 0,
            "not_found": 0,
            "errors": 0,
        }

    async def load_gis_permits(
        self,
        session: aiohttp.ClientSession,
        max_features: Optional[int] = None,
        progress: Optional[Progress] = None,
    ) -> int:
        """
        Pre-load all GIS permits into cache for faster matching.

        Args:
            session: aiohttp session
            max_features: Maximum permits to load
            progress: Rich progress bar

        Returns:
            Number of permits loaded
        """
        task = None
        if progress:
            task = progress.add_task("[cyan]Loading GIS permits...", total=None)

        def update_progress(fetched: int, total: int):
            if progress and task:
                progress.update(task, total=total, completed=fetched)

        permits = await self.fetcher.fetch_building_permits(
            session,
            max_features=max_features,
            progress_callback=update_progress if progress else None,
        )

        # Index by address fragments for faster lookup
        for permit in permits:
            if permit.address:
                # Create multiple keys for partial matching
                address_lower = permit.address.lower()
                if address_lower not in self.permits_cache:
                    self.permits_cache[address_lower] = []
                self.permits_cache[address_lower].append(permit)

        if progress and task:
            progress.update(task, completed=len(permits))

        logger.info(f"Loaded {len(permits)} GIS permits into cache")
        return len(permits)

    def _find_matching_permits(
        self,
        address: str,
        street_name: str = "",
    ) -> List[GISBuildingPermit]:
        """
        Find GIS permits matching an address.

        Args:
            address: Full address to match
            street_name: Street name for fallback matching

        Returns:
            List of matching permits (best matches first)
        """
        matches = []
        address_lower = address.lower() if address else ""
        street_lower = street_name.lower() if street_name else ""

        for cached_address, permits in self.permits_cache.items():
            # Check for address match
            if address_lower and address_lower in cached_address:
                matches.extend(permits)
            elif address_lower and cached_address in address_lower:
                matches.extend(permits)
            # Fall back to street name match
            elif street_lower and street_lower in cached_address:
                matches.extend(permits)

        # Remove duplicates while preserving order
        seen = set()
        unique_matches = []
        for permit in matches:
            if permit.object_id not in seen:
                seen.add(permit.object_id)
                unique_matches.append(permit)

        return unique_matches

    def enrich_record(
        self,
        record: Dict[str, Any],
    ) -> EnrichedBuildingRecord:
        """
        Enrich a single building record with GIS data.

        Args:
            record: Building record dict from Complot

        Returns:
            EnrichedBuildingRecord with GIS data
        """
        tik_number = record.get("tik_number", "")
        address = record.get("address", "")
        street_name = record.get("street_name", "")

        enriched = EnrichedBuildingRecord(
            tik_number=tik_number,
            address=address,
            gush=record.get("gush", ""),
            helka=record.get("helka", ""),
            street_code=record.get("street_code", 0),
            street_name=street_name,
        )

        # Find matching GIS permits
        matches = self._find_matching_permits(address, street_name)

        if matches:
            # Use the best match (first one)
            best_match = matches[0]

            enriched.permit_number = best_match.permit_number
            enriched.permit_date = best_match.permit_date
            enriched.permit_expiry = best_match.permit_expiry
            enriched.housing_units = best_match.housing_units
            enriched.permit_stage = best_match.permit_stage
            enriched.building_code = best_match.building_code
            enriched.geometry = best_match.geometry
            enriched.centroid = best_match.centroid
            enriched.gis_source = self.gis_source
            enriched.gis_object_id = best_match.object_id
            enriched.match_method = "address"
            enriched.match_confidence = 1.0 if address.lower() == best_match.address.lower() else 0.7
            enriched.enriched = True
            enriched.enriched_at = datetime.now().isoformat()

            self.stats["enriched"] += 1
        else:
            self.stats["not_found"] += 1

        self.stats["total_records"] += 1
        return enriched

    async def enrich_records(
        self,
        records: List[Dict[str, Any]],
        session: aiohttp.ClientSession,
        progress: Optional[Progress] = None,
    ) -> List[EnrichedBuildingRecord]:
        """
        Enrich multiple building records.

        Args:
            records: List of building record dicts
            session: aiohttp session
            progress: Rich progress bar

        Returns:
            List of EnrichedBuildingRecord
        """
        # Load GIS data if not already cached
        if not self.permits_cache:
            await self.load_gis_permits(session, progress=progress)

        task = None
        if progress:
            task = progress.add_task(
                "[green]Enriching records...",
                total=len(records)
            )

        enriched_records = []
        for record in records:
            enriched = self.enrich_record(record)
            enriched_records.append(enriched)

            if progress and task:
                progress.advance(task)

        return enriched_records

    def get_stats(self) -> Dict[str, Any]:
        """Get enrichment statistics."""
        return {
            **self.stats,
            "cache_size": len(self.permits_cache),
            "enrichment_rate": (
                self.stats["enriched"] / self.stats["total_records"]
                if self.stats["total_records"] > 0 else 0
            ),
        }


async def enrich_building_records(
    input_file: Path,
    output_file: Path,
    gis_source: str = "telaviv",
    max_gis_features: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Enrich building records from a JSON file.

    Args:
        input_file: Path to input JSON file with building records
        output_file: Path to output JSON file
        gis_source: GIS source to use
        max_gis_features: Maximum GIS features to load

    Returns:
        Enrichment statistics
    """
    # Load input records
    with open(input_file) as f:
        records = json.load(f)

    if not records:
        logger.warning("No records to enrich")
        return {"error": "No records found"}

    logger.info(f"Loaded {len(records)} records from {input_file}")

    # Create enricher
    enricher = BuildingEnricher(gis_source)

    # Run enrichment
    connector = aiohttp.TCPConnector(limit=10)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        async with aiohttp.ClientSession(connector=connector) as session:
            enriched = await enricher.enrich_records(
                records, session, progress=progress
            )

    # Save output
    output_data = [r.to_dict() for r in enriched]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"Saved {len(enriched)} enriched records to {output_file}")

    return enricher.get_stats()


# CLI entry point
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Enrich building records with GIS data"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Input JSON file with building records"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output JSON file (default: input_enriched.json)"
    )
    parser.add_argument(
        "--source",
        choices=["telaviv"],
        default="telaviv",
        help="GIS data source to use"
    )
    parser.add_argument(
        "--max-gis",
        type=int,
        default=None,
        help="Maximum GIS features to load"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Determine output file
    if args.output is None:
        args.output = args.input_file.parent / f"{args.input_file.stem}_enriched.json"

    # Run enrichment
    console.print(f"[bold]Enriching records from {args.input_file}[/bold]")
    console.print(f"GIS Source: {args.source}")
    console.print(f"Output: {args.output}")
    console.print()

    stats = asyncio.run(enrich_building_records(
        args.input_file,
        args.output,
        gis_source=args.source,
        max_gis_features=args.max_gis,
    ))

    console.print()
    console.print("[bold]Enrichment Statistics:[/bold]")
    console.print(f"  Total records: {stats.get('total_records', 0)}")
    console.print(f"  Enriched: {stats.get('enriched', 0)}")
    console.print(f"  Not found: {stats.get('not_found', 0)}")
    console.print(f"  Enrichment rate: {stats.get('enrichment_rate', 0):.1%}")


if __name__ == "__main__":
    main()
