"""
Direct API crawler for ofaqim.complot.co.il building permit data.

The actual data comes from:
https://handasi.complot.co.il/magicscripts/mgrqispi.dll?appname=cixpa&prgname=GetTikimByAddress&...

Parameters:
  - siteid: Site ID (67 for Ofakim)
  - c: City/Council code
  - s: Street code
  - h: House number
  - l: Flag (true/false)
"""

import asyncio
import json
import re
import csv
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path

import httpx
from bs4 import BeautifulSoup


@dataclass
class BuildingRecord:
    tik_number: str  # Building file number
    address: str
    gush: str  # Block
    helka: str  # Parcel
    migrash: str  # Plot
    archive_link: Optional[str]
    params: dict


@dataclass
class CrawlParams:
    siteid: int = 67
    c: int = 31  # city/council code
    s: int = 389  # street code
    h: int = 4  # house number
    l: bool = True


class BuildingPermitAPICrawler:
    API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.results: list[BuildingRecord] = []

    def _build_url(self, params: CrawlParams) -> str:
        """Build the API URL."""
        l_str = "true" if params.l else "false"
        return (
            f"{self.API_BASE}?appname=cixpa&prgname=GetTikimByAddress"
            f"&siteid={params.siteid}&c={params.c}&s={params.s}&h={params.h}&l={l_str}"
            f"&arguments=siteid,c,s,h,l"
        )

    def _parse_response(self, html: str, params: CrawlParams) -> list[BuildingRecord]:
        """Parse the HTML response and extract building records."""
        records = []
        soup = BeautifulSoup(html, "html.parser")

        # Find the results table
        table = soup.find("table", {"id": "results-table"})
        if not table:
            return records

        # Find all data rows (skip header)
        tbody = table.find("tbody")
        if not tbody:
            # Try to find rows directly in table
            rows = table.find_all("tr")[1:]  # Skip header
        else:
            rows = tbody.find_all("tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 6:
                # Extract archive link if present
                archive_cell = cells[6] if len(cells) > 6 else cells[-1]
                archive_link = None
                link = archive_cell.find("a")
                if link and link.get("href"):
                    archive_link = link.get("href")

                record = BuildingRecord(
                    tik_number=cells[1].get_text(strip=True) if len(cells) > 1 else "",
                    address=cells[2].get_text(strip=True) if len(cells) > 2 else "",
                    gush=cells[3].get_text(strip=True) if len(cells) > 3 else "",
                    helka=cells[4].get_text(strip=True) if len(cells) > 4 else "",
                    migrash=cells[5].get_text(strip=True) if len(cells) > 5 else "",
                    archive_link=archive_link,
                    params=asdict(params)
                )
                records.append(record)

        return records

    async def fetch_single(self, params: CrawlParams) -> list[BuildingRecord]:
        """Fetch data for a single set of parameters."""
        url = self._build_url(params)
        print(f"Fetching: c={params.c}, s={params.s}, h={params.h}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                records = self._parse_response(response.text, params)
                print(f"  Found {len(records)} records")
                return records
            except httpx.HTTPError as e:
                print(f"  Error: {e}")
                return []

    async def crawl_range(
        self,
        siteid: int = 67,
        c_values: list[int] = None,
        s_values: list[int] = None,
        h_range: range = None,
        concurrent_limit: int = 5,
        output_file: str = "results.json"
    ) -> list[BuildingRecord]:
        """
        Crawl multiple parameter combinations.

        Args:
            siteid: Site ID (67 for Ofakim)
            c_values: List of city/council codes
            s_values: List of street codes
            h_range: Range of house numbers
            concurrent_limit: Max concurrent requests
            output_file: Where to save results
        """
        c_values = c_values or [31]
        s_values = s_values or [389]
        h_range = h_range or range(1, 101)

        all_records = []
        semaphore = asyncio.Semaphore(concurrent_limit)

        async def fetch_with_semaphore(params: CrawlParams):
            async with semaphore:
                return await self.fetch_single(params)

        # Build all parameter combinations
        param_list = [
            CrawlParams(siteid=siteid, c=c, s=s, h=h)
            for c in c_values
            for s in s_values
            for h in h_range
        ]

        print(f"Total requests to make: {len(param_list)}")

        # Fetch in batches
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            tasks = []
            for params in param_list:
                task = fetch_with_semaphore(params)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, list):
                    all_records.extend(result)
                elif isinstance(result, Exception):
                    print(f"Error: {result}")

        # Save results
        self._save_results(all_records, output_file)
        self.results = all_records
        return all_records

    def _save_results(self, records: list[BuildingRecord], output_file: str):
        """Save results to JSON and CSV."""
        # Save as JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in records], f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(records)} records to {output_file}")

        # Also save as CSV
        csv_file = output_file.replace(".json", ".csv")
        if records:
            with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=asdict(records[0]).keys())
                writer.writeheader()
                for record in records:
                    writer.writerow(asdict(record))
            print(f"Saved CSV to {csv_file}")


async def discover_streets(siteid: int = 67, c: int = 31) -> list[int]:
    """
    Try to discover valid street codes by testing a range.
    Returns list of street codes that returned results.
    """
    crawler = BuildingPermitAPICrawler()
    valid_streets = []

    # Test street codes in a range
    for s in range(1, 500):
        params = CrawlParams(siteid=siteid, c=c, s=s, h=1)
        records = await crawler.fetch_single(params)
        if records:
            valid_streets.append(s)
            print(f"  Street {s} has data!")

    return valid_streets


async def main():
    crawler = BuildingPermitAPICrawler()

    # Example 1: Fetch single address
    print("=" * 60)
    print("Fetching single address...")
    print("=" * 60)

    params = CrawlParams(siteid=67, c=31, s=389, h=4, l=True)
    records = await crawler.fetch_single(params)

    for record in records:
        print(f"\nBuilding File: {record.tik_number}")
        print(f"Address: {record.address}")
        print(f"Block: {record.gush}")
        print(f"Parcel: {record.helka}")
        print(f"Plot: {record.migrash}")
        print(f"Archive: {record.archive_link}")

    # Example 2: Crawl a range of house numbers
    print("\n" + "=" * 60)
    print("Crawling range of house numbers (1-20)...")
    print("=" * 60)

    all_records = await crawler.crawl_range(
        siteid=67,
        c_values=[31],
        s_values=[389],
        h_range=range(1, 21),
        concurrent_limit=5,
        output_file="building_records.json"
    )

    print(f"\nTotal records found: {len(all_records)}")


if __name__ == "__main__":
    asyncio.run(main())
