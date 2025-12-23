"""
Full city crawler for Ofakim building permits.
Crawls all discovered streets and house numbers.
"""

import asyncio
import json
import csv
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup


API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"


@dataclass
class BuildingRecord:
    tik_number: str  # Building file number
    address: str
    gush: str  # Block
    helka: str  # Parcel
    migrash: str  # Plot
    archive_link: Optional[str]
    street_code: int
    street_name: str
    house_number: int


class FullCityCrawler:
    def __init__(
        self,
        siteid: int = 67,
        city_code: int = 31,
        concurrent_limit: int = 10,
        delay_between_batches: float = 0.5,
        max_house_number: int = 300
    ):
        self.siteid = siteid
        self.city_code = city_code
        self.concurrent_limit = concurrent_limit
        self.delay = delay_between_batches
        self.max_house_number = max_house_number
        self.stats = {
            "requests": 0,
            "records_found": 0,
            "errors": 0,
            "streets_completed": 0
        }

    def _parse_response(
        self,
        html: str,
        street_code: int,
        street_name: str,
        house_number: int
    ) -> list[BuildingRecord]:
        """Parse the HTML response and extract building records."""
        records = []
        soup = BeautifulSoup(html, "html.parser")

        table = soup.find("table", {"id": "results-table"})
        if not table:
            return records

        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 6:
                archive_link = None
                archive_cell = cells[6] if len(cells) > 6 else cells[-1]
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
                    street_code=street_code,
                    street_name=street_name,
                    house_number=house_number
                )
                records.append(record)

        return records

    async def fetch_address(
        self,
        client: httpx.AsyncClient,
        street_code: int,
        street_name: str,
        house_number: int
    ) -> list[BuildingRecord]:
        """Fetch building records for a single address."""
        url = (
            f"{API_BASE}?appname=cixpa&prgname=GetTikimByAddress"
            f"&siteid={self.siteid}&c={self.city_code}&s={street_code}&h={house_number}&l=true"
            f"&arguments=siteid,c,s,h,l"
        )

        try:
            response = await client.get(url)
            response.raise_for_status()
            self.stats["requests"] += 1

            records = self._parse_response(response.text, street_code, street_name, house_number)
            self.stats["records_found"] += len(records)
            return records

        except Exception as e:
            self.stats["errors"] += 1
            return []

    async def crawl_street(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        street: dict,
        all_records: list
    ):
        """Crawl all house numbers for a single street."""
        street_code = street["code"]
        street_name = street["name"]
        street_records = []

        # Crawl house numbers in batches
        for h in range(1, self.max_house_number + 1):
            async with semaphore:
                records = await self.fetch_address(client, street_code, street_name, h)
                if records:
                    street_records.extend(records)
                    all_records.extend(records)

        self.stats["streets_completed"] += 1
        if street_records:
            print(f"  Street {street_code} ({street_name}): {len(street_records)} records")

        return street_records

    async def crawl_city(
        self,
        streets_file: str = "discovered_streets.json",
        output_file: str = "ofakim_building_records.json"
    ) -> list[BuildingRecord]:
        """Crawl the entire city."""

        # Load discovered streets
        with open(streets_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            streets = data["streets"]

        print(f"{'=' * 60}")
        print(f"FULL CITY CRAWL - OFAKIM")
        print(f"{'=' * 60}")
        print(f"Streets to crawl: {len(streets)}")
        print(f"House numbers per street: 1-{self.max_house_number}")
        print(f"Max concurrent requests: {self.concurrent_limit}")
        print(f"Estimated total requests: {len(streets) * self.max_house_number}")
        print(f"{'=' * 60}\n")

        all_records = []
        semaphore = asyncio.Semaphore(self.concurrent_limit)

        async with httpx.AsyncClient(timeout=30) as client:
            # Process streets in groups for better progress reporting
            batch_size = 10
            for i in range(0, len(streets), batch_size):
                batch = streets[i:i + batch_size]
                print(f"\nProcessing streets {i + 1}-{min(i + batch_size, len(streets))} of {len(streets)}...")

                tasks = [
                    self.crawl_street(client, semaphore, street, all_records)
                    for street in batch
                ]
                await asyncio.gather(*tasks)

                # Progress report
                print(f"Progress: {self.stats['streets_completed']}/{len(streets)} streets, "
                      f"{self.stats['records_found']} records, "
                      f"{self.stats['requests']} requests, "
                      f"{self.stats['errors']} errors")

                # Save intermediate results
                self._save_results(all_records, output_file)

                # Small delay between batches to be polite to the server
                await asyncio.sleep(self.delay)

        print(f"\n{'=' * 60}")
        print(f"CRAWL COMPLETE")
        print(f"{'=' * 60}")
        print(f"Total records: {len(all_records)}")
        print(f"Total requests: {self.stats['requests']}")
        print(f"Errors: {self.stats['errors']}")

        return all_records

    def _save_results(self, records: list[BuildingRecord], output_file: str):
        """Save results to JSON and CSV."""
        # Save JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "crawled_at": datetime.now().isoformat(),
                    "total_records": len(records),
                    "stats": self.stats,
                    "records": [asdict(r) for r in records]
                },
                f,
                ensure_ascii=False,
                indent=2
            )

        # Save CSV
        csv_file = output_file.replace(".json", ".csv")
        if records:
            with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
                fieldnames = list(asdict(records[0]).keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for record in records:
                    writer.writerow(asdict(record))


async def main():
    crawler = FullCityCrawler(
        siteid=67,
        city_code=31,
        concurrent_limit=15,  # Concurrent requests
        delay_between_batches=0.3,  # Delay between street batches
        max_house_number=200  # Max house number to try per street
    )

    records = await crawler.crawl_city(
        streets_file="discovered_streets.json",
        output_file="ofakim_building_records.json"
    )

    print(f"\nResults saved to:")
    print(f"  - ofakim_building_records.json")
    print(f"  - ofakim_building_records.csv")


if __name__ == "__main__":
    asyncio.run(main())
