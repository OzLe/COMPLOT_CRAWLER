#!/usr/bin/env python3
"""
Unified multi-city crawler for Israeli municipality Complot building permit systems.

Usage:
    python main.py <city_name_or_url> [options]

Examples:
    python main.py batyam
    python main.py "https://batyam.complot.co.il/iturbakashot/#..."
    python main.py ofaqim --streets-only
    python main.py --list-cities
"""

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup

from src.city_config import CityConfig, get_city_config, list_cities, CITIES

# API Configuration
API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
MAX_CONCURRENT = 20
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
SAVE_INTERVAL = 100


@dataclass
class BuildingRecord:
    """A building file record from the search results"""
    tik_number: str
    address: str = ""
    gush: str = ""
    helka: str = ""
    migrash: str = ""
    street_code: int = 0
    street_name: str = ""
    house_number: int = 0


@dataclass
class BuildingDetail:
    """Detailed building file information"""
    tik_number: str
    address: str = ""
    neighborhood: str = ""
    addresses: list = field(default_factory=list)
    gush_helka: list = field(default_factory=list)
    plans: list = field(default_factory=list)
    requests: list = field(default_factory=list)
    stakeholders: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    fetch_status: str = "pending"
    fetch_error: str = ""
    fetched_at: str = ""


class ComplotCrawler:
    """Unified crawler for Complot building permit systems"""

    def __init__(self, config: CityConfig, output_dir: str = "data"):
        self.config = config
        # Create city-specific subdirectory
        self.output_dir = Path(output_dir) / config.name_en
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Output file names
        self.streets_file = self.output_dir / "streets.json"
        self.records_file = self.output_dir / "building_records.json"
        self.details_file = self.output_dir / "building_details.json"
        self.checkpoint_file = self.output_dir / "checkpoint.json"

    def _build_url(self, program: str, **params) -> str:
        """Build API URL with parameters"""
        param_str = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{API_BASE}?appname=cixpa&prgname={program}&{param_str}"

    async def _test_street(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        street_code: int
    ) -> Optional[dict]:
        """Test if a street code is valid"""
        async with semaphore:
            house_numbers = [1, 2, 3, 5, 10, 20, 50]

            for h in house_numbers:
                if self.config.api_type == "tikim":
                    url = self._build_url(
                        "GetTikimByAddress",
                        siteid=self.config.site_id,
                        c=self.config.city_code,
                        s=street_code,
                        h=h,
                        l="true",
                        arguments="siteid,c,s,h,l"
                    )
                else:  # bakashot
                    url = self._build_url(
                        "GetBakashotByAddress",
                        siteid=self.config.site_id,
                        grp=0,
                        t=1,
                        c=self.config.city_code,
                        s=street_code,
                        h=h,
                        l="true",
                        arguments="siteId,grp,t,c,s,h,l"
                    )

                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')
                        text = soup.get_text()

                        # Check for results
                        if "נמצאו" in text and ("תיקי בניין" in text or "בקשות" in text):
                            # Extract street name
                            table = soup.find("table", {"id": "results-table"})
                            if table:
                                rows = table.select("tbody tr")
                                if rows:
                                    cells = rows[0].find_all("td")
                                    # For bakashot API, address is in a specific column containing city name
                                    # For tikim API, it's usually column 2
                                    addr = None
                                    for cell in cells:
                                        cell_text = cell.get_text(strip=True)
                                        # Address should contain the city name
                                        if self.config.name in cell_text:
                                            addr = cell_text
                                            break

                                    if addr:
                                        # Extract street name (remove house number and city)
                                        # Format: "STREET NUM CITY" or "STREET CITY"
                                        parts = addr.replace(self.config.name, '').strip().rsplit(' ', 1)
                                        street_name = parts[0].strip() if parts else addr
                                        # Clean up the street name
                                        if street_name and len(street_name) > 1:
                                            return {"code": street_code, "name": street_name}
                except Exception:
                    continue

            return None

    async def discover_streets(self, force: bool = False) -> list[dict]:
        """Discover all valid street codes for the city"""
        if self.streets_file.exists() and not force:
            print(f"Loading cached streets from {self.streets_file}")
            with open(self.streets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('streets', [])

        print(f"\n{'='*60}")
        print(f"DISCOVERING STREETS FOR {self.config.name} ({self.config.name_en})")
        print(f"{'='*60}")
        print(f"Site ID: {self.config.site_id}")
        print(f"City Code: {self.config.city_code}")
        print(f"Street range: {self.config.street_range[0]} - {self.config.street_range[1]}")
        print(f"{'='*60}\n")

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        streets = []
        start, end = self.config.street_range

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                self._test_street(session, semaphore, s)
                for s in range(start, end + 1)
            ]

            batch_size = 100
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                results = await asyncio.gather(*batch, return_exceptions=True)

                for result in results:
                    if isinstance(result, dict) and result:
                        streets.append(result)
                        print(f"  Found street {result['code']}: {result['name']}")

                progress = min(i + batch_size, len(tasks))
                print(f"Progress: {progress}/{len(tasks)} codes tested ({len(streets)} streets found)")

        # Save streets
        output = {
            "city": self.config.name,
            "city_en": self.config.name_en,
            "site_id": self.config.site_id,
            "city_code": self.config.city_code,
            "discovered_at": datetime.now().isoformat(),
            "total_streets": len(streets),
            "streets": sorted(streets, key=lambda x: x["code"])
        }

        with open(self.streets_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\nDiscovered {len(streets)} streets. Saved to {self.streets_file}")
        return streets

    async def _fetch_records_for_street(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        street: dict
    ) -> list[BuildingRecord]:
        """Fetch all building records for a street"""
        records = []
        street_code = street['code']
        street_name = street['name']

        async with semaphore:
            for house_num in range(1, 500):  # Try house numbers 1-499
                if self.config.api_type == "tikim":
                    url = self._build_url(
                        "GetTikimByAddress",
                        siteid=self.config.site_id,
                        c=self.config.city_code,
                        s=street_code,
                        h=house_num,
                        l="true",
                        arguments="siteid,c,s,h,l"
                    )
                else:
                    url = self._build_url(
                        "GetBakashotByAddress",
                        siteid=self.config.site_id,
                        grp=0,
                        t=1,
                        c=self.config.city_code,
                        s=street_code,
                        h=house_num,
                        l="true",
                        arguments="siteId,grp,t,c,s,h,l"
                    )

                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Check for no results
                        if "לא אותרו" in soup.get_text() or "לא ניתן" in soup.get_text():
                            continue

                        # Parse results table
                        table = soup.find("table", {"id": "results-table"})
                        if not table:
                            continue

                        rows = table.select("tbody tr")
                        for row in rows:
                            cells = row.find_all("td")
                            if len(cells) < 3:
                                continue

                            # Extract tik number from link
                            tik = None

                            # Look for getBuilding link (has tik number)
                            for link in row.find_all("a", href=True):
                                href = str(link.get("href", ""))
                                if "getBuilding" in href:
                                    match = re.search(r'getBuilding\((\d+)\)', href)
                                    if match:
                                        tik = match.group(1)
                                        break

                            if not tik:
                                # For tikim API, first link might be the tik
                                link = row.find("a", href=True)
                                if link:
                                    text = link.get_text(strip=True)
                                    if text.isdigit():
                                        tik = text
                                    else:
                                        match = re.search(r'\d+', text)
                                        if match:
                                            tik = match.group()

                            if not tik:
                                continue

                            # Get address - look for cell containing city name
                            address = ""
                            for cell in cells:
                                text = cell.get_text(strip=True)
                                if self.config.name in text:
                                    address = text
                                    break

                            # Get gush/helka if available (usually in last columns)
                            gush = ""
                            helka = ""
                            # Look for numeric cells at the end that could be gush/helka
                            numeric_cells = []
                            for cell in reversed(cells):
                                text = cell.get_text(strip=True)
                                if text.isdigit() and len(text) <= 6:
                                    numeric_cells.append(text)
                                elif numeric_cells:
                                    break
                            if len(numeric_cells) >= 2:
                                helka = numeric_cells[0]
                                gush = numeric_cells[1]

                            record = BuildingRecord(
                                tik_number=tik,
                                address=address,
                                gush=gush,
                                helka=helka,
                                street_code=street_code,
                                street_name=street_name,
                                house_number=house_num
                            )
                            records.append(record)

                except Exception:
                    continue

        return records

    async def fetch_building_records(self, streets: list[dict], force: bool = False) -> list[BuildingRecord]:
        """Fetch all building records for all streets"""
        if self.records_file.exists() and not force:
            print(f"Loading cached records from {self.records_file}")
            with open(self.records_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [BuildingRecord(**r) for r in data.get('records', [])]

        print(f"\n{'='*60}")
        print(f"FETCHING BUILDING RECORDS FOR {self.config.name}")
        print(f"{'='*60}")
        print(f"Total streets: {len(streets)}")
        print(f"{'='*60}\n")

        all_records = []
        seen_tiks = set()
        semaphore = asyncio.Semaphore(5)  # Lower concurrency for full street scans
        start_time = time.time()

        connector = aiohttp.TCPConnector(limit=20)
        async with aiohttp.ClientSession(connector=connector) as session:
            for i, street in enumerate(streets):
                records = await self._fetch_records_for_street(session, semaphore, street)

                # Deduplicate
                for r in records:
                    if r.tik_number not in seen_tiks:
                        seen_tiks.add(r.tik_number)
                        all_records.append(r)

                elapsed = time.time() - start_time
                print(f"Street {i+1}/{len(streets)}: {street['name']} - {len(records)} records ({len(all_records)} total)")

                # Save checkpoint every 10 streets
                if (i + 1) % 10 == 0:
                    self._save_records_checkpoint(all_records)

        # Save final records
        output = {
            "city": self.config.name,
            "city_en": self.config.name_en,
            "crawled_at": datetime.now().isoformat(),
            "total_records": len(all_records),
            "records": [asdict(r) for r in all_records]
        }

        with open(self.records_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\nFetched {len(all_records)} unique building records. Saved to {self.records_file}")
        return all_records

    def _save_records_checkpoint(self, records: list[BuildingRecord]):
        """Save records checkpoint"""
        output = {
            "city": self.config.name,
            "checkpoint_at": datetime.now().isoformat(),
            "total_records": len(records),
            "records": [asdict(r) for r in records]
        }
        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

    def _parse_building_detail(self, html: str, tik_number: str) -> BuildingDetail:
        """Parse building detail HTML response"""
        soup = BeautifulSoup(html, 'html.parser')
        detail = BuildingDetail(tik_number=tik_number)
        detail.fetched_at = datetime.now().isoformat()

        # Extract address from header
        header_divs = soup.select('#result-title-div-id .top-navbar-info-desc')
        for i, div in enumerate(header_divs):
            if 'כתובת' in div.get_text():
                if i + 1 < len(header_divs):
                    detail.address = header_divs[i + 1].get_text(strip=True)

        # Extract neighborhood
        info_main = soup.select_one('#info-main')
        if info_main:
            for row in info_main.select('tr'):
                cells = row.select('td')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    if 'שכונה' in label:
                        detail.neighborhood = value

        # Extract addresses
        addresses_div = soup.select_one('#addresses')
        if addresses_div:
            for row in addresses_div.select('tbody tr'):
                addr = row.get_text(strip=True)
                if addr:
                    detail.addresses.append(addr)

        # Extract gush/helka
        gush_table = soup.select_one('#table-gushim-helkot')
        if gush_table:
            for row in gush_table.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 5:
                    gush_info = {
                        'gush': cells[1].get_text(strip=True),
                        'helka': cells[2].get_text(strip=True),
                        'migrash': cells[3].get_text(strip=True),
                        'plan_number': cells[4].get_text(strip=True)
                    }
                    if gush_info['gush']:
                        detail.gush_helka.append(gush_info)

        # Extract requests/permits
        requests_table = soup.select_one('#table-requests')
        if requests_table:
            for row in requests_table.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 7:
                    request_info = {
                        'request_number': cells[1].get_text(strip=True),
                        'submission_date': cells[2].get_text(strip=True),
                        'last_event': cells[3].get_text(strip=True),
                        'applicant_name': cells[4].get_text(strip=True),
                        'permit_number': cells[5].get_text(strip=True),
                        'permit_date': cells[6].get_text(strip=True)
                    }
                    if request_info['request_number']:
                        detail.requests.append(request_info)

        # Extract plans
        plans_table = soup.select_one('#table-taba')
        if plans_table:
            for row in plans_table.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 5 and 'לא אותרו' not in row.get_text():
                    plan_info = {
                        'plan_number': cells[1].get_text(strip=True),
                        'plan_name': cells[2].get_text(strip=True),
                        'status': cells[3].get_text(strip=True),
                        'status_date': cells[4].get_text(strip=True)
                    }
                    if plan_info['plan_number']:
                        detail.plans.append(plan_info)

        detail.fetch_status = "success"
        return detail

    async def _fetch_single_detail(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        tik_number: str,
        retry: int = 0
    ) -> BuildingDetail:
        """Fetch details for a single building"""
        async with semaphore:
            url = self._build_url(
                "GetTikFile",
                siteid=self.config.site_id,
                t=tik_number,
                arguments="siteid,t"
            )

            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        return self._parse_building_detail(html, tik_number)
                    else:
                        detail = BuildingDetail(tik_number=tik_number)
                        detail.fetch_status = "error"
                        detail.fetch_error = f"HTTP {resp.status}"
                        return detail

            except asyncio.TimeoutError:
                if retry < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                    return await self._fetch_single_detail(session, semaphore, tik_number, retry + 1)
                detail = BuildingDetail(tik_number=tik_number)
                detail.fetch_status = "error"
                detail.fetch_error = "Timeout"
                return detail

            except Exception as e:
                detail = BuildingDetail(tik_number=tik_number)
                detail.fetch_status = "error"
                detail.fetch_error = str(e)
                return detail

    async def fetch_building_details(self, records: list[BuildingRecord], resume: bool = True) -> list[BuildingDetail]:
        """Fetch detailed information for all building records"""
        tik_numbers = list(set(r.tik_number for r in records))

        # Load checkpoint if resuming
        completed = {}
        if resume and self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'details' in data:
                        completed = {d['tik_number']: BuildingDetail(**d) for d in data['details']}
            except Exception:
                pass

        remaining = [t for t in tik_numbers if t not in completed]

        print(f"\n{'='*60}")
        print(f"FETCHING BUILDING DETAILS FOR {self.config.name}")
        print(f"{'='*60}")
        print(f"Total tiks: {len(tik_numbers)}")
        print(f"Already completed: {len(completed)}")
        print(f"Remaining: {len(remaining)}")
        print(f"{'='*60}\n")

        if not remaining:
            print("All details already fetched!")
            return list(completed.values())

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        start_time = time.time()

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
        async with aiohttp.ClientSession(connector=connector) as session:
            batch_size = SAVE_INTERVAL

            for batch_idx in range(0, len(remaining), batch_size):
                batch = remaining[batch_idx:batch_idx + batch_size]
                tasks = [self._fetch_single_detail(session, semaphore, tik) for tik in batch]
                results = await asyncio.gather(*tasks)

                for result in results:
                    completed[result.tik_number] = result

                processed = batch_idx + len(batch)
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - processed) / rate if rate > 0 else 0

                success = sum(1 for r in results if r.fetch_status == 'success')
                errors = sum(1 for r in results if r.fetch_status == 'error')

                print(f"Progress: {processed}/{len(remaining)} ({100*processed/len(remaining):.1f}%) | "
                      f"Rate: {rate:.1f}/sec | ETA: {eta/60:.1f} min | Batch: {success} ok, {errors} errors")

                # Save checkpoint
                self._save_details_checkpoint(list(completed.values()))

        # Save final results
        all_details = list(completed.values())
        output = {
            "city": self.config.name,
            "city_en": self.config.name_en,
            "fetched_at": datetime.now().isoformat(),
            "total_records": len(all_details),
            "success_count": sum(1 for d in all_details if d.fetch_status == 'success'),
            "error_count": sum(1 for d in all_details if d.fetch_status == 'error'),
            "records": [asdict(d) for d in all_details]
        }

        with open(self.details_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\nFetched {len(all_details)} building details. Saved to {self.details_file}")
        return all_details

    def _save_details_checkpoint(self, details: list[BuildingDetail]):
        """Save details checkpoint"""
        checkpoint = {
            "city": self.config.name,
            "checkpoint_at": datetime.now().isoformat(),
            "total": len(details),
            "details": [asdict(d) for d in details]
        }
        checkpoint_file = self.output_dir / "details_checkpoint.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)

    def export_csv(self, details: list[BuildingDetail]):
        """Export results to CSV files"""
        # Main details CSV
        csv_file = self.output_dir / "buildings.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['tik_number', 'address', 'neighborhood', 'num_requests', 'num_plans'])
            for d in details:
                writer.writerow([d.tik_number, d.address, d.neighborhood, len(d.requests), len(d.plans)])

        # Permits CSV
        permits_file = self.output_dir / "permits.csv"
        with open(permits_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['tik_number', 'address', 'request_number', 'submission_date',
                           'last_event', 'applicant_name', 'permit_number', 'permit_date'])
            for d in details:
                for req in d.requests:
                    writer.writerow([
                        d.tik_number, d.address,
                        req['request_number'], req['submission_date'],
                        req['last_event'], req['applicant_name'],
                        req['permit_number'], req['permit_date']
                    ])

        print(f"Exported CSV files: {csv_file}, {permits_file}")

    async def run_full_crawl(self, streets_only: bool = False, skip_details: bool = False, force: bool = False):
        """Run the complete crawl process"""
        print(f"\n{'#'*60}")
        print(f"# COMPLOT CRAWLER - {self.config.name} ({self.config.name_en})")
        print(f"{'#'*60}")
        print(f"# Site ID: {self.config.site_id}")
        print(f"# City Code: {self.config.city_code}")
        print(f"# API Type: {self.config.api_type}")
        print(f"# Output Directory: {self.output_dir}")
        print(f"{'#'*60}\n")

        # Step 1: Discover streets
        streets = await self.discover_streets(force=force)

        if streets_only:
            print("\nStreets-only mode. Stopping here.")
            return

        # Step 2: Fetch building records
        records = await self.fetch_building_records(streets, force=force)

        if skip_details:
            print("\nSkipping details fetch.")
            return

        # Step 3: Fetch building details
        details = await self.fetch_building_details(records)

        # Step 4: Export CSV
        self.export_csv(details)

        print(f"\n{'#'*60}")
        print(f"# CRAWL COMPLETE")
        print(f"{'#'*60}")
        print(f"# City: {self.config.name}")
        print(f"# Streets: {len(streets)}")
        print(f"# Building Records: {len(records)}")
        print(f"# Building Details: {len(details)}")
        print(f"{'#'*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Crawl Israeli municipality Complot building permit systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py batyam
  python main.py ofaqim --streets-only
  python main.py "https://batyam.complot.co.il/..."
  python main.py --list-cities
        """
    )

    parser.add_argument("city", nargs="?", help="City name or Complot URL")
    parser.add_argument("--list-cities", action="store_true", help="List available cities")
    parser.add_argument("--streets-only", action="store_true", help="Only discover streets")
    parser.add_argument("--skip-details", action="store_true", help="Skip detailed info fetch")
    parser.add_argument("--force", action="store_true", help="Force re-fetch even if cached")
    parser.add_argument("--output-dir", default="data", help="Output directory (default: data/)")

    args = parser.parse_args()

    if args.list_cities:
        print("\nAvailable cities:")
        print("-" * 70)
        print(f"{'Key':15} | {'Name':12} | {'Site ID':8} | {'City Code':10}")
        print("-" * 70)
        for city in list_cities():
            print(f"{city['key']:15} | {city['name']:12} | {city['site_id']:8} | {city['city_code']:10}")
        print("-" * 70)
        print("\nUsage: python main.py <city_key>")
        return

    if not args.city:
        parser.print_help()
        return

    try:
        config = get_city_config(args.city)
    except ValueError as e:
        print(f"Error: {e}")
        print("\nUse --list-cities to see available cities")
        return

    crawler = ComplotCrawler(config, args.output_dir)
    asyncio.run(crawler.run_full_crawl(
        streets_only=args.streets_only,
        skip_details=args.skip_details,
        force=args.force
    ))


if __name__ == "__main__":
    main()
