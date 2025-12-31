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
import json
import multiprocessing
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, MofNCompleteColumn

# Rich console for phase headers
console = Console()

def create_progress() -> Progress:
    """Create a Rich progress bar with consistent styling"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("<"),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )

from src.config import CityConfig, get_city_config, list_cities
from src.config import DEFAULT_SETTINGS
from src.models import BuildingRecord, BuildingDetail, RequestDetail
from src.utils.logging import setup_logging, get_logger
from src.storage import CheckpointManager, DataExporter
from src.fetchers.street_fetcher import async_discover_range
from src.fetchers.record_fetcher import async_fetch_records_for_street
from src.fetchers.building_fetcher import async_fetch_details_batch
from src.fetchers.request_fetcher import async_fetch_request_detail, async_fetch_requests_batch

# API Configuration (using settings for consistency, will be fully migrated later)
_settings = DEFAULT_SETTINGS
API_BASE = _settings.api_base
MAX_CONCURRENT = _settings.max_concurrent
REQUEST_TIMEOUT = _settings.request_timeout
MAX_RETRIES = _settings.max_retries
RETRY_DELAY = _settings.retry_delay
SAVE_INTERVAL = _settings.save_interval

# Logger setup (using centralized logging from src.utils.logging)
logger = get_logger()


# ============================================================================
# MULTIPROCESSING WORKER FUNCTIONS
# These must be at module level to be picklable for multiprocessing.Pool
# ============================================================================

async def _async_discover_range(config_dict: dict, start: int, end: int) -> list[dict]:
    """Async street discovery for a specific range (delegates to fetchers.street_fetcher)"""
    return await async_discover_range(config_dict, start, end)


def _worker_discover_streets(args: tuple) -> list[dict]:
    """Worker function for street discovery - runs in separate process"""
    config_dict, start, end, worker_id = args
    result = asyncio.run(_async_discover_range(config_dict, start, end))
    return result


async def _async_fetch_records_for_street(session: aiohttp.ClientSession, config_dict: dict, street: dict) -> list[dict]:
    """Fetch all building records for a single street (delegates to fetchers.record_fetcher)"""
    return await async_fetch_records_for_street(session, config_dict, street)


async def _async_fetch_records_batch(config_dict: dict, streets: list[dict]) -> list[dict]:
    """Async records fetch for a batch of streets (worker function)"""
    all_records = []
    semaphore = asyncio.Semaphore(5)

    async def fetch_with_semaphore(session, street):
        async with semaphore:
            return await async_fetch_records_for_street(session, config_dict, street)

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        for street in streets:
            records = await fetch_with_semaphore(session, street)
            all_records.extend(records)

    return all_records


def _worker_fetch_records(args: tuple) -> list[dict]:
    """Worker function for building records - runs in separate process"""
    config_dict, streets, worker_id = args
    result = asyncio.run(_async_fetch_records_batch(config_dict, streets))
    return result


async def _async_fetch_single_request(
    session: aiohttp.ClientSession,
    config_dict: dict,
    request_number: str,
    tik_number: str = ""
) -> dict:
    """Fetch a single request detail (delegates to fetchers.request_fetcher)"""
    return await async_fetch_request_detail(session, config_dict, request_number, tik_number)


async def _async_fetch_requests_batch(config_dict: dict, request_items: list[tuple]) -> list[dict]:
    """Async request details fetch (delegates to fetchers.request_fetcher)"""
    return await async_fetch_requests_batch(config_dict, request_items)


def _worker_fetch_requests(args: tuple) -> list[dict]:
    """Worker function for request details - runs in separate process"""
    config_dict, request_items, worker_id = args
    result = asyncio.run(_async_fetch_requests_batch(config_dict, request_items))
    return result


async def _async_fetch_details_batch(config_dict: dict, tik_numbers: list[str]) -> list[dict]:
    """Async details fetch (delegates to fetchers.building_fetcher)"""
    return await async_fetch_details_batch(config_dict, tik_numbers)


def _worker_fetch_details(args: tuple) -> list[dict]:
    """Worker function for building details - runs in separate process"""
    config_dict, tik_numbers, worker_id = args
    result = asyncio.run(_async_fetch_details_batch(config_dict, tik_numbers))
    return result


# ============================================================================
# END OF MULTIPROCESSING WORKER FUNCTIONS
# ============================================================================


class ComplotCrawler:
    """Unified crawler for Complot building permit systems"""

    def __init__(self, config: CityConfig, output_dir: str = "data", israeli_id: Optional[str] = None, workers: int = 1):
        self.config = config
        self.israeli_id = israeli_id
        self.workers = max(1, workers)  # Ensure at least 1 worker
        # Create city-specific subdirectory
        self.output_dir = Path(output_dir) / config.name_en
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize storage utilities
        self.checkpoint = CheckpointManager(self.output_dir, config.name, config.name_en)
        self.exporter = DataExporter(self.output_dir, config.name, config.name_en)

        # File paths for reading cached data
        self.streets_file = self.output_dir / "streets.json"
        self.records_file = self.output_dir / "building_records.json"
        self.details_file = self.output_dir / "building_details.json"

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

    async def _run_discovery(self) -> list[dict]:
        """Run the actual street discovery process (API calls)"""
        logger.info("=" * 60)
        logger.info(f"DISCOVERING STREETS FOR {self.config.name} ({self.config.name_en})")
        logger.info("=" * 60)
        logger.info(f"Site ID: {self.config.site_id}")
        logger.info(f"City Code: {self.config.city_code}")
        logger.info(f"Street range: {self.config.street_range[0]} - {self.config.street_range[1]}")

        start, end = self.config.street_range
        start_time = time.time()
        streets = []

        if self.workers > 1:
            # Multi-process mode: split range across workers
            logger.info(f"Using {self.workers} workers for parallel street discovery")
            total_range = end - start + 1
            # Use small fixed chunk size for granular progress updates
            chunk_size = 100  # Small chunks for responsive progress bar

            # Create ranges for each chunk
            ranges = []
            for chunk_start in range(start, end + 1, chunk_size):
                chunk_end = min(chunk_start + chunk_size - 1, end)
                ranges.append((chunk_start, chunk_end))

            # Prepare config dict for workers (must be picklable)
            config_dict = asdict(self.config)

            # Prepare worker arguments
            worker_args = [(config_dict, r[0], r[1], i) for i, r in enumerate(ranges)]
            # Calculate actual range sizes for accurate progress
            range_sizes = [r[1] - r[0] + 1 for r in ranges]

            # Run workers in parallel with progress bar
            with multiprocessing.Pool(self.workers) as pool:
                with create_progress() as progress:
                    task = progress.add_task("[cyan]Discovering streets", total=total_range)
                    for i, result in enumerate(pool.imap(_worker_discover_streets, worker_args)):
                        streets.extend(result)
                        # Update by actual range size (handles uneven chunks)
                        progress.update(task, advance=range_sizes[i], description=f"[cyan]Discovering streets [found={len(streets)}]")

            elapsed = time.time() - start_time
            logger.info(f"All workers completed in {elapsed:.1f}s. Total streets found: {len(streets)}")

        else:
            # Single-process mode: original async implementation
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
            async with aiohttp.ClientSession(connector=connector) as session:
                tasks = [
                    self._test_street(session, semaphore, s)
                    for s in range(start, end + 1)
                ]

                batch_size = 100

                with create_progress() as progress:
                    task = progress.add_task("[cyan]Discovering streets", total=len(tasks))
                    for i in range(0, len(tasks), batch_size):
                        batch = tasks[i:i + batch_size]
                        results = await asyncio.gather(*batch, return_exceptions=True)

                        for result in results:
                            if isinstance(result, dict) and result:
                                streets.append(result)
                                logger.debug(f"Found street {result['code']}: {result['name']}")

                        progress.update(task, advance=len(batch), description=f"[cyan]Discovering streets [found={len(streets)}]")

        return streets

    async def discover_streets(self, force: bool = False) -> tuple[list[dict], list[dict]]:
        """
        Discover all valid street codes for the city.

        Returns:
            tuple: (all_streets, new_streets)
            - all_streets: Complete list of discovered streets
            - new_streets: Streets that are new since last run (empty if no baseline or force=True)
        """
        baseline_streets = []
        baseline_codes = set()
        previous_total = 0

        # Load baseline for comparison (if exists and not forcing)
        if self.streets_file.exists() and not force:
            logger.info(f"Loading baseline streets from {self.streets_file} for incremental detection")
            with open(self.streets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                baseline_streets = data.get('streets', [])
                baseline_codes = {s['code'] for s in baseline_streets}
                previous_total = len(baseline_streets)
                logger.info(f"Baseline has {previous_total} streets")

        # Run fresh discovery
        fresh_streets = await self._run_discovery()
        fresh_codes = {s['code'] for s in fresh_streets}

        # Compute diff
        new_codes = fresh_codes - baseline_codes
        removed_codes = baseline_codes - fresh_codes
        new_streets = [s for s in fresh_streets if s['code'] in new_codes]

        # Log changes
        if new_streets:
            logger.info(f"Found {len(new_streets)} NEW streets:")
            for s in new_streets:
                logger.info(f"  + {s['code']}: {s['name']}")
        elif baseline_streets:
            logger.info("No new streets found since last run")

        if removed_codes:
            logger.warning(f"Found {len(removed_codes)} streets that no longer exist: {removed_codes}")

        # Save streets with incremental metadata
        sorted_streets = sorted(fresh_streets, key=lambda x: x["code"])
        self.exporter.export_streets(sorted_streets, new_streets, previous_total)

        logger.info(f"Discovered {len(sorted_streets)} streets (previous: {previous_total}, new: {len(new_streets)}). Saved to {self.streets_file}")
        return sorted_streets, new_streets

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
            logger.info(f"Loading cached records from {self.records_file}")
            with open(self.records_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [BuildingRecord(**r) for r in data.get('records', [])]

        logger.info("=" * 60)
        logger.info(f"FETCHING BUILDING RECORDS FOR {self.config.name}")
        logger.info("=" * 60)
        logger.info(f"Total streets: {len(streets)}")

        all_records = []
        seen_tiks = set()
        start_time = time.time()

        if self.workers > 1 and len(streets) > 1:
            # Multi-process mode: split streets across workers
            logger.info(f"Using {self.workers} workers for parallel records fetching")

            # Use small fixed chunk size for granular progress updates
            # Each chunk completes quickly, providing frequent progress updates
            chunk_size = 10  # Small chunks for responsive progress bar
            street_chunks = []
            for i in range(0, len(streets), chunk_size):
                chunk = streets[i:i + chunk_size]
                if chunk:
                    street_chunks.append(chunk)

            # Prepare config dict for workers
            config_dict = asdict(self.config)

            # Prepare worker arguments
            worker_args = [(config_dict, chunk, i) for i, chunk in enumerate(street_chunks)]

            # Run workers in parallel with progress bar
            with multiprocessing.Pool(self.workers) as pool:
                with create_progress() as progress:
                    task = progress.add_task("[green]Fetching records", total=len(streets))
                    for i, result in enumerate(pool.imap(_worker_fetch_records, worker_args)):
                        # Merge and deduplicate results
                        for r in result:
                            if r['tik_number'] not in seen_tiks:
                                seen_tiks.add(r['tik_number'])
                                all_records.append(BuildingRecord(**r))
                        # Update by actual chunk size (handles uneven last chunk)
                        actual_chunk_size = len(street_chunks[i])
                        progress.update(task, advance=actual_chunk_size, description=f"[green]Fetching records [records={len(all_records)}]")

            elapsed = time.time() - start_time
            logger.info(f"All workers completed in {elapsed:.1f}s. Total records found: {len(all_records)}")

        else:
            # Single-process mode: original async implementation
            semaphore = asyncio.Semaphore(5)  # Lower concurrency for full street scans

            connector = aiohttp.TCPConnector(limit=20)
            async with aiohttp.ClientSession(connector=connector) as session:
                with create_progress() as progress:
                    task = progress.add_task("[green]Fetching records", total=len(streets))
                    for i, street in enumerate(streets):
                        records = await self._fetch_records_for_street(session, semaphore, street)

                        # Deduplicate
                        new_records = 0
                        for r in records:
                            if r.tik_number not in seen_tiks:
                                seen_tiks.add(r.tik_number)
                                all_records.append(r)
                                new_records += 1

                        progress.update(task, advance=1, description=f"[green]Fetching records [records={len(all_records)}]")

                        # Save checkpoint every 10 streets
                        if (i + 1) % 10 == 0:
                            logger.debug(f"Saving checkpoint at street {i+1}")
                            self.checkpoint.save_records(all_records)

        # Save final records
        self.exporter.export_records(all_records)

        logger.info(f"Fetched {len(all_records)} unique building records. Saved to {self.records_file}")
        return all_records

    def _parse_building_detail(self, html: str, tik_number: str) -> BuildingDetail:
        """Parse building detail HTML response"""
        soup = BeautifulSoup(html, 'html.parser')
        detail = BuildingDetail(tik_number=tik_number)
        detail.fetched_at = datetime.now().isoformat()

        # Check for error responses
        text = soup.get_text()
        if 'לא ניתן להציג את המידע המבוקש' in text or 'לא אותרו תוצאות' in text:
            detail.fetch_status = "error"
            detail.fetch_error = "No data available"
            return detail

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

    def _parse_bakasha_detail(self, html: str, tik_number: str) -> BuildingDetail:
        """Parse bakasha (request) detail HTML response"""
        soup = BeautifulSoup(html, 'html.parser')
        detail = BuildingDetail(tik_number=tik_number)
        detail.fetched_at = datetime.now().isoformat()

        # Check for error responses
        text = soup.get_text()
        if 'לא ניתן להציג את המידע המבוקש' in text or 'לא אותרו תוצאות' in text:
            detail.fetch_status = "error"
            detail.fetch_error = "No data available"
            return detail

        if 'מספר תעודת הזהות' in text or 'אנא הזינו' in text:
            detail.fetch_status = "error"
            detail.fetch_error = "Authentication required"
            return detail

        # Extract address from header (similar structure to tikim)
        header_divs = soup.select('#result-title-div-id .top-navbar-info-desc')
        for i, div in enumerate(header_divs):
            if 'כתובת' in div.get_text():
                if i + 1 < len(header_divs):
                    detail.address = header_divs[i + 1].get_text(strip=True)

        # Try alternate address location
        if not detail.address:
            addr_elem = soup.select_one('.address-value, .bakasha-address')
            if addr_elem:
                detail.address = addr_elem.get_text(strip=True)

        # Extract from info tables
        info_tables = soup.select('table')
        for table in info_tables:
            for row in table.select('tr'):
                cells = row.select('td, th')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)

                    if 'כתובת' in label and not detail.address:
                        detail.address = value
                    elif 'שכונה' in label:
                        detail.neighborhood = value

        # Extract request/permit info
        # Look for request details table
        requests_table = soup.select_one('#table-requests, .requests-table, #bakashot-table')
        if requests_table:
            for row in requests_table.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 6:
                    request_info = {
                        'request_number': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                        'submission_date': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                        'last_event': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                        'applicant_name': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                        'permit_number': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                        'permit_date': cells[5].get_text(strip=True) if len(cells) > 5 else ''
                    }
                    if request_info['request_number']:
                        detail.requests.append(request_info)

        # If no table found, try to extract single request info from the page
        if not detail.requests:
            # Look for individual fields
            request_info = {}
            for table in info_tables:
                for row in table.select('tr'):
                    cells = row.select('td')
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)

                        if 'מספר בקשה' in label or 'מס בקשה' in label:
                            request_info['request_number'] = value
                        elif 'תאריך הגשה' in label:
                            request_info['submission_date'] = value
                        elif 'סטטוס' in label or 'אירוע אחרון' in label:
                            request_info['last_event'] = value
                        elif 'מבקש' in label or 'שם מגיש' in label:
                            request_info['applicant_name'] = value
                        elif 'מספר היתר' in label:
                            request_info['permit_number'] = value
                        elif 'תאריך היתר' in label:
                            request_info['permit_date'] = value

            if request_info.get('request_number'):
                detail.requests.append({
                    'request_number': request_info.get('request_number', ''),
                    'submission_date': request_info.get('submission_date', ''),
                    'last_event': request_info.get('last_event', ''),
                    'applicant_name': request_info.get('applicant_name', ''),
                    'permit_number': request_info.get('permit_number', ''),
                    'permit_date': request_info.get('permit_date', '')
                })

        # Extract gush/helka if available
        gush_table = soup.select_one('#table-gushim-helkot, .gush-table')
        if gush_table:
            for row in gush_table.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 3:
                    gush_info = {
                        'gush': cells[0].get_text(strip=True) if len(cells) > 0 else '',
                        'helka': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                        'migrash': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                        'plan_number': cells[3].get_text(strip=True) if len(cells) > 3 else ''
                    }
                    if gush_info['gush']:
                        detail.gush_helka.append(gush_info)

        detail.fetch_status = "success"
        return detail

    async def _fetch_single_bakasha_detail(
        self,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        request_number: str,
        israeli_id: str,
        retry: int = 0
    ) -> BuildingDetail:
        """Fetch details for a single bakasha (request) with ID authentication"""
        async with semaphore:
            url = self._build_url(
                "GetBakashaFile",
                siteid=self.config.site_id,
                ession=request_number,
                ession2=israeli_id,
                arguments="siteid,ession,ession2"
            )

            headers = {
                "Referer": self.config.base_url,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }

            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
                    if resp.status == 200:
                        html = await resp.text()
                        return self._parse_bakasha_detail(html, request_number)
                    else:
                        detail = BuildingDetail(tik_number=request_number)
                        detail.fetch_status = "error"
                        detail.fetch_error = f"HTTP {resp.status}"
                        return detail

            except asyncio.TimeoutError:
                if retry < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                    return await self._fetch_single_bakasha_detail(session, semaphore, request_number, israeli_id, retry + 1)
                detail = BuildingDetail(tik_number=request_number)
                detail.fetch_status = "error"
                detail.fetch_error = "Timeout"
                return detail

            except Exception as e:
                detail = BuildingDetail(tik_number=request_number)
                detail.fetch_status = "error"
                detail.fetch_error = str(e)
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

            # Add referer header for the request
            headers = {
                "Referer": self.config.base_url,
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }

            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
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

        # For bakashot systems, detailed info requires authentication
        if self.config.api_type == "bakashot":
            if not self.israeli_id:
                logger.warning("Bakashot API requires ID authentication for permit details")
                logger.warning("Use --id <israeli_id> to fetch full permit information")
                logger.info("Using building records data for basic details")
                details = []
                for r in records:
                    detail = BuildingDetail(
                        tik_number=r.tik_number,
                        address=r.address,
                        addresses=[r.address] if r.address else [],
                        gush_helka=[{
                            'gush': r.gush,
                            'helka': r.helka,
                            'migrash': r.migrash,
                            'plan_number': ''
                        }] if r.gush else [],
                        fetch_status="from_records",
                        fetched_at=datetime.now().isoformat()
                    )
                    details.append(detail)
                return details
            else:
                # Use authenticated bakasha API
                logger.info("Using authenticated bakashot API with provided ID")
                return await self._fetch_bakasha_details_authenticated(records, resume)

        tik_numbers = list(set(r.tik_number for r in records))

        # Load checkpoint if resuming
        completed = {}
        if resume:
            data = self.checkpoint.load_details_checkpoint()
            if 'details' in data:
                completed = {d['tik_number']: BuildingDetail(**d) for d in data['details']}

        remaining = [t for t in tik_numbers if t not in completed]

        logger.info("=" * 60)
        logger.info(f"FETCHING BUILDING DETAILS FOR {self.config.name}")
        logger.info("=" * 60)
        logger.info(f"Total tiks: {len(tik_numbers)}")
        logger.info(f"Already completed: {len(completed)}")
        logger.info(f"Remaining: {len(remaining)}")

        if not remaining:
            logger.info("All details already fetched!")
            return list(completed.values())

        start_time = time.time()
        total_success = 0
        total_errors = 0

        if self.workers > 1 and len(remaining) > 1:
            # Multi-process mode: split tik numbers across workers
            logger.info(f"Using {self.workers} workers for parallel details fetching")

            # Use small fixed chunk size for granular progress updates
            chunk_size = 20  # Small chunks for responsive progress bar
            tik_chunks = []
            for i in range(0, len(remaining), chunk_size):
                chunk = remaining[i:i + chunk_size]
                if chunk:
                    tik_chunks.append(chunk)

            # Prepare config dict for workers
            config_dict = asdict(self.config)

            # Prepare worker arguments
            worker_args = [(config_dict, chunk, i) for i, chunk in enumerate(tik_chunks)]

            # Run workers in parallel with progress bar
            with multiprocessing.Pool(self.workers) as pool:
                with create_progress() as progress:
                    task = progress.add_task("[yellow]Fetching details", total=len(remaining))
                    for i, result in enumerate(pool.imap(_worker_fetch_details, worker_args)):
                        # Merge results
                        for d in result:
                            detail = BuildingDetail(**d)
                            completed[d['tik_number']] = detail
                            if d['fetch_status'] == 'success':
                                total_success += 1
                            else:
                                total_errors += 1
                        # Update by actual chunk size
                        progress.update(task, advance=len(tik_chunks[i]), description=f"[yellow]Fetching details [ok={total_success}, err={total_errors}]")

            elapsed = time.time() - start_time
            logger.info(f"All workers completed in {elapsed:.1f}s. Total details fetched: {len(remaining)}")

        else:
            # Single-process mode: original async implementation
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
            async with aiohttp.ClientSession(connector=connector) as session:
                batch_size = SAVE_INTERVAL

                with create_progress() as progress:
                    task = progress.add_task("[yellow]Fetching details", total=len(remaining))
                    for batch_idx in range(0, len(remaining), batch_size):
                        batch = remaining[batch_idx:batch_idx + batch_size]

                        tasks = [self._fetch_single_detail(session, semaphore, tik) for tik in batch]
                        results = await asyncio.gather(*tasks)

                        for result in results:
                            completed[result.tik_number] = result

                        success = sum(1 for r in results if r.fetch_status == 'success')
                        errors = sum(1 for r in results if r.fetch_status == 'error')
                        total_success += success
                        total_errors += errors

                        # Log any errors in this batch
                        for r in results:
                            if r.fetch_status == 'error':
                                logger.debug(f"Error fetching tik {r.tik_number}: {r.fetch_error}")

                        progress.update(task, advance=len(batch), description=f"[yellow]Fetching details [ok={total_success}, err={total_errors}]")

                        # Save checkpoint
                        logger.debug(f"Saving checkpoint with {len(completed)} records")
                        self.checkpoint.save_details(list(completed.values()))

        # Save final results
        all_details = list(completed.values())
        self.exporter.export_details(all_details)

        logger.info(f"Fetched {len(all_details)} building details ({total_success} ok, {total_errors} errors). Saved to {self.details_file}")
        return all_details

    async def retry_failed_details(self) -> list[BuildingDetail]:
        """Retry fetching only the records that previously failed"""
        if not self.details_file.exists():
            logger.error(f"No details file found at {self.details_file}. Run a full crawl first.")
            return []

        # Load existing details
        with open(self.details_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        all_details = {d['tik_number']: BuildingDetail(**d) for d in data.get('records', [])}
        failed_tiks = [tik for tik, detail in all_details.items() if detail.fetch_status == 'error']

        if not failed_tiks:
            logger.info("No failed records to retry!")
            return list(all_details.values())

        logger.info("=" * 60)
        logger.info(f"RETRYING FAILED DETAILS FOR {self.config.name}")
        logger.info("=" * 60)
        logger.info(f"Total records: {len(all_details)}")
        logger.info(f"Failed records to retry: {len(failed_tiks)}")

        start_time = time.time()
        total_success = 0
        total_errors = 0

        if self.workers > 1 and len(failed_tiks) > 1:
            # Multi-process mode
            logger.info(f"Using {self.workers} workers for parallel retry")

            # Use small fixed chunk size for granular progress updates
            chunk_size = 20  # Small chunks for responsive progress bar
            tik_chunks = []
            for i in range(0, len(failed_tiks), chunk_size):
                chunk = failed_tiks[i:i + chunk_size]
                if chunk:
                    tik_chunks.append(chunk)

            config_dict = asdict(self.config)
            worker_args = [(config_dict, chunk, i) for i, chunk in enumerate(tik_chunks)]

            with multiprocessing.Pool(self.workers) as pool:
                with create_progress() as progress:
                    task = progress.add_task("[yellow]Retrying failed", total=len(failed_tiks))
                    for i, result in enumerate(pool.imap(_worker_fetch_details, worker_args)):
                        for d in result:
                            detail = BuildingDetail(**d)
                            all_details[d['tik_number']] = detail
                            if d['fetch_status'] == 'success':
                                total_success += 1
                            else:
                                total_errors += 1
                        # Update by actual chunk size
                        progress.update(task, advance=len(tik_chunks[i]), description=f"[yellow]Retrying failed [ok={total_success}, err={total_errors}]")

        else:
            # Single-process mode
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

            async with aiohttp.ClientSession(connector=connector) as session:
                batch_size = SAVE_INTERVAL

                with create_progress() as progress:
                    task = progress.add_task("[yellow]Retrying failed", total=len(failed_tiks))
                    for batch_idx in range(0, len(failed_tiks), batch_size):
                        batch = failed_tiks[batch_idx:batch_idx + batch_size]

                        tasks = [self._fetch_single_detail(session, semaphore, tik) for tik in batch]
                        results = await asyncio.gather(*tasks)

                        for result in results:
                            all_details[result.tik_number] = result
                            if result.fetch_status == 'success':
                                total_success += 1
                            else:
                                total_errors += 1

                        progress.update(task, advance=len(batch), description=f"[yellow]Retrying failed [ok={total_success}, err={total_errors}]")

        # Save updated results
        details_list = list(all_details.values())
        self.exporter.export_details(details_list)

        elapsed = time.time() - start_time
        success_count = sum(1 for d in details_list if d.fetch_status == 'success')
        error_count = sum(1 for d in details_list if d.fetch_status == 'error')
        logger.info(f"Retry complete in {elapsed:.1f}s. Retried {len(failed_tiks)}: {total_success} ok, {total_errors} still failing")
        logger.info(f"Total: {success_count} ok, {error_count} errors. Saved to {self.details_file}")

        return details_list

    async def fetch_request_details(self, building_details: list[BuildingDetail], force: bool = False) -> list[RequestDetail]:
        """Fetch detailed permit information for all requests found in building details.

        This calls GetBakashaFile for each request_number found in building_details.requests,
        extracting rich permit data including events, stakeholders, requirements, and decisions.
        """
        # Extract all unique (request_number, tik_number) pairs from building details
        request_items = []
        seen_requests = set()
        for detail in building_details:
            if detail.fetch_status != 'success':
                continue
            for req in detail.requests:
                req_num = req.get('request_number', '')
                if req_num and req_num not in seen_requests:
                    seen_requests.add(req_num)
                    request_items.append((req_num, detail.tik_number))

        if not request_items:
            logger.info("No requests found in building details to fetch")
            return []

        # Load existing request details if not forcing
        requests_file = self.output_dir / "request_details.json"
        completed = {}
        if not force:
            data = self.checkpoint.load_requests_checkpoint(requests_file)
            for r in data.get('records', []):
                completed[r['request_number']] = RequestDetail(**r)

        # Filter out already fetched requests
        remaining = [(req_num, tik_num) for req_num, tik_num in request_items if req_num not in completed]

        logger.info("=" * 60)
        logger.info(f"FETCHING REQUEST DETAILS FOR {self.config.name}")
        logger.info("=" * 60)
        logger.info(f"Total unique requests: {len(request_items)}")
        logger.info(f"Already completed: {len(completed)}")
        logger.info(f"Remaining: {len(remaining)}")

        if not remaining:
            logger.info("All request details already fetched!")
            return list(completed.values())

        start_time = time.time()
        total_success = 0
        total_errors = 0

        if self.workers > 1 and len(remaining) > 1:
            # Multi-process mode
            logger.info(f"Using {self.workers} workers for parallel request fetching")

            # Use small fixed chunk size for granular progress updates
            chunk_size = 20  # Small chunks for responsive progress bar
            request_chunks = []
            for i in range(0, len(remaining), chunk_size):
                chunk = remaining[i:i + chunk_size]
                if chunk:
                    request_chunks.append(chunk)

            config_dict = asdict(self.config)
            worker_args = [(config_dict, chunk, i) for i, chunk in enumerate(request_chunks)]

            with multiprocessing.Pool(self.workers) as pool:
                with create_progress() as progress:
                    task = progress.add_task("[magenta]Fetching requests", total=len(remaining))
                    for i, result in enumerate(pool.imap(_worker_fetch_requests, worker_args)):
                        for r in result:
                            detail = RequestDetail(**r)
                            completed[r['request_number']] = detail
                            if r['fetch_status'] == 'success':
                                total_success += 1
                            else:
                                total_errors += 1
                        # Update by actual chunk size
                        progress.update(task, advance=len(request_chunks[i]), description=f"[magenta]Fetching requests [ok={total_success}, err={total_errors}]")

            elapsed = time.time() - start_time
            logger.info(f"All workers completed in {elapsed:.1f}s")

        else:
            # Single-process mode
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

            async with aiohttp.ClientSession(connector=connector) as session:
                batch_size = SAVE_INTERVAL

                with create_progress() as progress:
                    task = progress.add_task("[magenta]Fetching requests", total=len(remaining))
                    for batch_idx in range(0, len(remaining), batch_size):
                        batch = remaining[batch_idx:batch_idx + batch_size]

                        async def fetch_one(req_num: str, tik_num: str):
                            async with semaphore:
                                return await _async_fetch_single_request(session, asdict(self.config), req_num, tik_num)

                        tasks = [fetch_one(req_num, tik_num) for req_num, tik_num in batch]
                        results = await asyncio.gather(*tasks)

                        for result in results:
                            detail = RequestDetail(**result)
                            completed[result['request_number']] = detail
                            if result['fetch_status'] == 'success':
                                total_success += 1
                            else:
                                total_errors += 1

                        progress.update(task, advance=len(batch), description=f"[magenta]Fetching requests [ok={total_success}, err={total_errors}]")

                        # Save checkpoint periodically
                        self.checkpoint.save_requests(list(completed.values()), requests_file)

        # Save final results
        all_requests = list(completed.values())
        self.exporter.export_requests(all_requests)

        elapsed = time.time() - start_time
        logger.info(f"Fetched {len(all_requests)} request details ({total_success} ok, {total_errors} errors) in {elapsed:.1f}s")
        logger.info(f"Saved to {requests_file}")

        return all_requests

    async def _fetch_bakasha_details_authenticated(self, records: list[BuildingRecord], resume: bool = True) -> list[BuildingDetail]:
        """Fetch bakasha details using authenticated API"""
        tik_numbers = list(set(r.tik_number for r in records))

        # Load checkpoint if resuming
        completed = {}
        if resume:
            data = self.checkpoint.load_details_checkpoint()
            if 'details' in data:
                completed = {d['tik_number']: BuildingDetail(**d) for d in data['details']}

        remaining = [t for t in tik_numbers if t not in completed]

        logger.info("=" * 60)
        logger.info(f"FETCHING BAKASHA DETAILS FOR {self.config.name} (Authenticated)")
        logger.info("=" * 60)
        logger.info(f"Total requests: {len(tik_numbers)}")
        logger.info(f"Already completed: {len(completed)}")
        logger.info(f"Remaining: {len(remaining)}")

        if not remaining:
            logger.info("All details already fetched!")
            return list(completed.values())

        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        start_time = time.time()
        total_success = 0
        total_errors = 0

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
        async with aiohttp.ClientSession(connector=connector) as session:
            batch_size = SAVE_INTERVAL

            with create_progress() as progress:
                task = progress.add_task("[magenta]Fetching bakasha details", total=len(remaining))
                for batch_idx in range(0, len(remaining), batch_size):
                    batch = remaining[batch_idx:batch_idx + batch_size]

                    tasks = [
                        self._fetch_single_bakasha_detail(session, semaphore, tik, self.israeli_id)
                        for tik in batch
                    ]
                    results = await asyncio.gather(*tasks)

                    for result in results:
                        completed[result.tik_number] = result

                    success = sum(1 for r in results if r.fetch_status == 'success')
                    errors = sum(1 for r in results if r.fetch_status == 'error')
                    total_success += success
                    total_errors += errors

                    # Log any errors in this batch
                    for r in results:
                        if r.fetch_status == 'error':
                            logger.debug(f"Error fetching request {r.tik_number}: {r.fetch_error}")

                    progress.update(task, advance=len(batch), description=f"[magenta]Fetching bakasha details [ok={total_success}, err={total_errors}]")

                    # Save checkpoint
                    logger.debug(f"Saving checkpoint with {len(completed)} records")
                    self.checkpoint.save_details(list(completed.values()))

        # Save final results
        all_details = list(completed.values())
        self.exporter.export_details(all_details)

        logger.info(f"Fetched {len(all_details)} bakasha details ({total_success} ok, {total_errors} errors). Saved to {self.details_file}")
        return all_details

    async def run_full_crawl(self, streets_only: bool = False, skip_details: bool = False, skip_requests: bool = False, force: bool = False, verbose: bool = False, retry_errors: bool = False):
        """Run the complete crawl process

        Phases:
        1. Discover streets (brute-force scan)
        2. Fetch building records (GetTikimByAddress)
        3. Fetch building details (GetTikFile)
        4. Fetch request details (GetBakashaFile) - detailed permit lifecycle
        5. Export CSV
        """
        # Initialize logging
        setup_logging(self.output_dir, verbose=verbose)

        logger.info("#" * 60)
        logger.info(f"COMPLOT CRAWLER - {self.config.name} ({self.config.name_en})")
        logger.info("#" * 60)
        logger.info(f"Site ID: {self.config.site_id}")
        logger.info(f"City Code: {self.config.city_code}")
        logger.info(f"API Type: {self.config.api_type}")
        logger.info(f"Output Directory: {self.output_dir}")
        logger.info(f"Workers: {self.workers}")

        # Handle retry-errors mode: only retry failed details, skip everything else
        if retry_errors:
            logger.info("RETRY-ERRORS MODE: Only retrying failed building details")
            details = await self.retry_failed_details()
            if details:
                self.exporter.export_csv(details)
            logger.info("#" * 60)
            logger.info("RETRY COMPLETE")
            logger.info("#" * 60)
            return

        # Step 1: Discover streets (returns all_streets and new_streets)
        console.rule("[bold cyan]Phase 1: Discovering Streets")
        all_streets, new_streets = await self.discover_streets(force=force)

        if streets_only:
            logger.info("Streets-only mode. Stopping here.")
            return

        # Step 2: Fetch building records
        console.rule("[bold green]Phase 2: Fetching Building Records")
        # If we have new streets and not forcing, do incremental fetch
        if new_streets and not force:
            logger.info("=" * 60)
            logger.info(f"INCREMENTAL MODE: Fetching records for {len(new_streets)} new streets only")
            logger.info("=" * 60)

            # Load existing records
            existing_records = []
            if self.records_file.exists():
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_records = [BuildingRecord(**r) for r in data.get('records', [])]
                logger.info(f"Loaded {len(existing_records)} existing records from cache")

            # Fetch records for new streets only (bypass cache with force=True)
            new_records = await self.fetch_building_records(new_streets, force=True)

            # Merge records (dedupe by tik_number)
            seen_tiks = {r.tik_number for r in existing_records}
            added_count = 0
            for r in new_records:
                if r.tik_number not in seen_tiks:
                    existing_records.append(r)
                    seen_tiks.add(r.tik_number)
                    added_count += 1

            records = existing_records
            logger.info(f"Merged {added_count} new records. Total: {len(records)}")

            # Save merged records
            output = {
                "city": self.config.name,
                "city_en": self.config.name_en,
                "crawled_at": datetime.now().isoformat(),
                "total_records": len(records),
                "records": [asdict(r) for r in records]
            }
            with open(self.records_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
        elif not new_streets and self.records_file.exists() and not force:
            # No new streets and cache exists - just load from cache
            logger.info("No new streets found. Loading records from cache.")
            with open(self.records_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                records = [BuildingRecord(**r) for r in data.get('records', [])]
        else:
            # Full fetch (no baseline, force, or first run)
            records = await self.fetch_building_records(all_streets, force=force)

        if skip_details:
            logger.info("Skipping details fetch.")
            return

        # Step 3: Fetch building details
        console.rule("[bold yellow]Phase 3: Fetching Building Details")
        details = await self.fetch_building_details(records)

        # Step 4: Fetch request details (permit lifecycle)
        request_details = []
        if not skip_requests:
            console.rule("[bold magenta]Phase 4: Fetching Request Details")
            request_details = await self.fetch_request_details(details, force=force)
        else:
            logger.info("Skipping request details fetch.")

        # Step 5: Export CSV
        self.exporter.export_csv(details, request_details)

        logger.info("#" * 60)
        logger.info("CRAWL COMPLETE")
        logger.info("#" * 60)
        logger.info(f"City: {self.config.name}")
        logger.info(f"Streets: {len(all_streets)}")
        logger.info(f"New Streets: {len(new_streets)}")
        logger.info(f"Building Records: {len(records)}")
        logger.info(f"Building Details: {len(details)}")
        logger.info(f"Request Details: {len(request_details)}")
        logger.info("#" * 60)


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
    parser.add_argument("--skip-details", action="store_true", help="Skip building details fetch (Phase 3)")
    parser.add_argument("--skip-requests", action="store_true", help="Skip request details fetch (Phase 4 - permit lifecycle)")
    parser.add_argument("--force", action="store_true", help="Force re-fetch even if cached")
    parser.add_argument("--output-dir", default="data", help="Output directory (default: data/)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging (debug level)")
    parser.add_argument("--id", dest="israeli_id", help="Israeli ID number for bakashot authentication (required for permit details in some cities)")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes for parallel crawling (default: 1)")
    parser.add_argument("--retry-errors", action="store_true", help="Retry fetching only the records that previously failed")

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

    crawler = ComplotCrawler(config, args.output_dir, israeli_id=args.israeli_id, workers=args.workers)
    asyncio.run(crawler.run_full_crawl(
        streets_only=args.streets_only,
        skip_details=args.skip_details,
        skip_requests=args.skip_requests,
        force=args.force,
        verbose=args.verbose,
        retry_errors=args.retry_errors
    ))


if __name__ == "__main__":
    main()
