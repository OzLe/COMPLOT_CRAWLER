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
import logging
import multiprocessing
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup
from tqdm import tqdm

from src.city_config import CityConfig, get_city_config, list_cities, CITIES

# API Configuration
API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
MAX_CONCURRENT = 20
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
SAVE_INTERVAL = 100

# Logger setup
logger = logging.getLogger("complot_crawler")


def setup_logging(output_dir: Path, verbose: bool = False):
    """Configure logging with console and file handlers"""
    log_level = logging.DEBUG if verbose else logging.INFO

    # Create formatter with timestamp
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # File handler
    log_file = output_dir / "crawler.log"
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)  # Always log debug to file
    file_handler.setFormatter(formatter)

    # Configure logger
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # Remove existing handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.info(f"Logging initialized. Log file: {log_file}")


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


# ============================================================================
# MULTIPROCESSING WORKER FUNCTIONS
# These must be at module level to be picklable for multiprocessing.Pool
# ============================================================================

def _build_url(program: str, **params) -> str:
    """Build API URL with parameters (standalone version for workers)"""
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{API_BASE}?appname=cixpa&prgname={program}&{param_str}"


async def _async_test_street(session: aiohttp.ClientSession, config_dict: dict, street_code: int) -> Optional[dict]:
    """Test if a street code is valid (standalone async function for workers)"""
    house_numbers = [1, 2, 3, 5, 10, 20, 50]
    city_name = config_dict['name']

    for h in house_numbers:
        if config_dict['api_type'] == "tikim":
            url = _build_url(
                "GetTikimByAddress",
                siteid=config_dict['site_id'],
                c=config_dict['city_code'],
                s=street_code,
                h=h,
                l="true",
                arguments="siteid,c,s,h,l"
            )
        else:  # bakashot
            url = _build_url(
                "GetBakashotByAddress",
                siteid=config_dict['site_id'],
                grp=0,
                t=1,
                c=config_dict['city_code'],
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

                if "נמצאו" in text and ("תיקי בניין" in text or "בקשות" in text):
                    table = soup.find("table", {"id": "results-table"})
                    if table:
                        rows = table.select("tbody tr")
                        if rows:
                            cells = rows[0].find_all("td")
                            addr = None
                            for cell in cells:
                                cell_text = cell.get_text(strip=True)
                                if city_name in cell_text:
                                    addr = cell_text
                                    break

                            if addr:
                                parts = addr.replace(city_name, '').strip().rsplit(' ', 1)
                                street_name = parts[0].strip() if parts else addr
                                if street_name and len(street_name) > 1:
                                    return {"code": street_code, "name": street_name}
        except Exception:
            continue

    return None


async def _async_discover_range(config_dict: dict, start: int, end: int) -> list[dict]:
    """Async street discovery for a specific range (worker function)"""
    streets = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def test_with_semaphore(session, street_code):
        async with semaphore:
            return await _async_test_street(session, config_dict, street_code)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_with_semaphore(session, s) for s in range(start, end + 1)]

        batch_size = 100
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    streets.append(result)

    return streets


def _worker_discover_streets(args: tuple) -> list[dict]:
    """Worker function for street discovery - runs in separate process"""
    config_dict, start, end, worker_id = args
    print(f"[Worker {worker_id}] Discovering streets {start}-{end}")
    result = asyncio.run(_async_discover_range(config_dict, start, end))
    print(f"[Worker {worker_id}] Found {len(result)} streets")
    return result


async def _async_fetch_records_for_street(session: aiohttp.ClientSession, config_dict: dict, street: dict) -> list[dict]:
    """Fetch all building records for a single street (worker function)"""
    records = []
    street_code = street['code']
    street_name = street['name']
    city_name = config_dict['name']

    for house_num in range(1, 500):
        if config_dict['api_type'] == "tikim":
            url = _build_url(
                "GetTikimByAddress",
                siteid=config_dict['site_id'],
                c=config_dict['city_code'],
                s=street_code,
                h=house_num,
                l="true",
                arguments="siteid,c,s,h,l"
            )
        else:
            url = _build_url(
                "GetBakashotByAddress",
                siteid=config_dict['site_id'],
                grp=0,
                t=1,
                c=config_dict['city_code'],
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

                if "לא אותרו" in soup.get_text() or "לא ניתן" in soup.get_text():
                    continue

                table = soup.find("table", {"id": "results-table"})
                if not table:
                    continue

                rows = table.select("tbody tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue

                    tik = None
                    for link in row.find_all("a", href=True):
                        href = str(link.get("href", ""))
                        if "getBuilding" in href:
                            match = re.search(r'getBuilding\((\d+)\)', href)
                            if match:
                                tik = match.group(1)
                                break

                    if not tik:
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

                    address = ""
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        if city_name in text:
                            address = text
                            break

                    gush = ""
                    helka = ""
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

                    records.append({
                        "tik_number": tik,
                        "address": address,
                        "gush": gush,
                        "helka": helka,
                        "migrash": "",
                        "street_code": street_code,
                        "street_name": street_name,
                        "house_number": house_num
                    })
        except Exception:
            continue

    return records


async def _async_fetch_records_batch(config_dict: dict, streets: list[dict]) -> list[dict]:
    """Async records fetch for a batch of streets (worker function)"""
    all_records = []
    semaphore = asyncio.Semaphore(5)  # Lower concurrency for full street scans

    async def fetch_with_semaphore(session, street):
        async with semaphore:
            return await _async_fetch_records_for_street(session, config_dict, street)

    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        for street in streets:
            records = await fetch_with_semaphore(session, street)
            all_records.extend(records)

    return all_records


def _worker_fetch_records(args: tuple) -> list[dict]:
    """Worker function for building records - runs in separate process"""
    config_dict, streets, worker_id = args
    print(f"[Worker {worker_id}] Fetching records for {len(streets)} streets")
    result = asyncio.run(_async_fetch_records_batch(config_dict, streets))
    print(f"[Worker {worker_id}] Found {len(result)} records")
    return result


async def _async_fetch_single_detail(session: aiohttp.ClientSession, config_dict: dict, tik_number: str, retry: int = 0) -> dict:
    """Fetch details for a single building (worker function)"""
    url = _build_url(
        "GetTikFile",
        siteid=config_dict['site_id'],
        t=tik_number,
        arguments="siteid,t"
    )

    headers = {
        "Referer": config_dict['base_url'],
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            if resp.status == 200:
                html = await resp.text()
                return _parse_building_detail_standalone(html, tik_number)
            else:
                return {
                    "tik_number": tik_number,
                    "fetch_status": "error",
                    "fetch_error": f"HTTP {resp.status}",
                    "fetched_at": datetime.now().isoformat()
                }
    except asyncio.TimeoutError:
        if retry < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY * (2 ** retry))
            return await _async_fetch_single_detail(session, config_dict, tik_number, retry + 1)
        return {
            "tik_number": tik_number,
            "fetch_status": "error",
            "fetch_error": "Timeout",
            "fetched_at": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "tik_number": tik_number,
            "fetch_status": "error",
            "fetch_error": str(e),
            "fetched_at": datetime.now().isoformat()
        }


def _parse_building_detail_standalone(html: str, tik_number: str) -> dict:
    """Parse building detail HTML response (standalone version for workers)"""
    soup = BeautifulSoup(html, 'html.parser')
    detail = {
        "tik_number": tik_number,
        "address": "",
        "neighborhood": "",
        "addresses": [],
        "gush_helka": [],
        "plans": [],
        "requests": [],
        "stakeholders": [],
        "documents": [],
        "fetch_status": "pending",
        "fetch_error": "",
        "fetched_at": datetime.now().isoformat()
    }

    text = soup.get_text()
    if 'לא ניתן להציג את המידע המבוקש' in text or 'לא אותרו תוצאות' in text:
        detail["fetch_status"] = "error"
        detail["fetch_error"] = "No data available"
        return detail

    # Extract address from header
    header_divs = soup.select('#result-title-div-id .top-navbar-info-desc')
    for i, div in enumerate(header_divs):
        if 'כתובת' in div.get_text():
            if i + 1 < len(header_divs):
                detail["address"] = header_divs[i + 1].get_text(strip=True)

    # Extract neighborhood
    info_main = soup.select_one('#info-main')
    if info_main:
        for row in info_main.select('tr'):
            cells = row.select('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if 'שכונה' in label:
                    detail["neighborhood"] = value

    # Extract addresses
    addresses_div = soup.select_one('#addresses')
    if addresses_div:
        for row in addresses_div.select('tbody tr'):
            addr = row.get_text(strip=True)
            if addr:
                detail["addresses"].append(addr)

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
                    detail["gush_helka"].append(gush_info)

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
                    detail["requests"].append(request_info)

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
                    detail["plans"].append(plan_info)

    detail["fetch_status"] = "success"
    return detail


async def _async_fetch_details_batch(config_dict: dict, tik_numbers: list[str]) -> list[dict]:
    """Async details fetch for a batch of tik numbers (worker function)"""
    details = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def fetch_with_semaphore(session, tik):
        async with semaphore:
            return await _async_fetch_single_detail(session, config_dict, tik)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_with_semaphore(session, tik) for tik in tik_numbers]

        batch_size = 100
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)

            for result in results:
                if isinstance(result, dict):
                    details.append(result)
                elif isinstance(result, Exception):
                    # Handle exception case
                    pass

    return details


def _worker_fetch_details(args: tuple) -> list[dict]:
    """Worker function for building details - runs in separate process"""
    config_dict, tik_numbers, worker_id = args
    print(f"[Worker {worker_id}] Fetching details for {len(tik_numbers)} buildings")
    result = asyncio.run(_async_fetch_details_batch(config_dict, tik_numbers))
    print(f"[Worker {worker_id}] Fetched {len(result)} details")
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
            chunk_size = max(1, total_range // self.workers)

            # Create ranges for each worker
            ranges = []
            for i in range(self.workers):
                chunk_start = start + i * chunk_size
                chunk_end = start + (i + 1) * chunk_size - 1 if i < self.workers - 1 else end
                if chunk_start <= end:
                    ranges.append((chunk_start, chunk_end))

            # Prepare config dict for workers (must be picklable)
            config_dict = asdict(self.config)

            # Prepare worker arguments
            worker_args = [(config_dict, r[0], r[1], i) for i, r in enumerate(ranges)]

            # Run workers in parallel with progress bar
            with multiprocessing.Pool(self.workers) as pool:
                with tqdm(total=total_range, desc="Discovering streets", unit="codes") as pbar:
                    for result in pool.imap_unordered(_worker_discover_streets, worker_args):
                        streets.extend(result)
                        # Update progress by chunk size (approximate)
                        pbar.update(chunk_size)
                        pbar.set_postfix(found=len(streets))

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

                with tqdm(total=len(tasks), desc="Discovering streets", unit="codes") as pbar:
                    for i in range(0, len(tasks), batch_size):
                        batch = tasks[i:i + batch_size]
                        results = await asyncio.gather(*batch, return_exceptions=True)

                        for result in results:
                            if isinstance(result, dict) and result:
                                streets.append(result)
                                logger.debug(f"Found street {result['code']}: {result['name']}")

                        pbar.update(len(batch))
                        pbar.set_postfix(found=len(streets))

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
        output = {
            "city": self.config.name,
            "city_en": self.config.name_en,
            "site_id": self.config.site_id,
            "city_code": self.config.city_code,
            "discovered_at": datetime.now().isoformat(),
            "total_streets": len(fresh_streets),
            "previous_total": previous_total,
            "new_streets_count": len(new_streets),
            "new_streets": sorted(new_streets, key=lambda x: x["code"]) if new_streets else [],
            "streets": sorted_streets
        }

        with open(self.streets_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        logger.info(f"Discovered {len(fresh_streets)} streets (previous: {previous_total}, new: {len(new_streets)}). Saved to {self.streets_file}")
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

            # Split streets into chunks for each worker
            chunk_size = max(1, len(streets) // self.workers)
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
                with tqdm(total=len(streets), desc="Fetching records", unit="streets") as pbar:
                    for result in pool.imap_unordered(_worker_fetch_records, worker_args):
                        # Merge and deduplicate results
                        for r in result:
                            if r['tik_number'] not in seen_tiks:
                                seen_tiks.add(r['tik_number'])
                                all_records.append(BuildingRecord(**r))
                        pbar.update(chunk_size)
                        pbar.set_postfix(records=len(all_records))

            elapsed = time.time() - start_time
            logger.info(f"All workers completed in {elapsed:.1f}s. Total records found: {len(all_records)}")

        else:
            # Single-process mode: original async implementation
            semaphore = asyncio.Semaphore(5)  # Lower concurrency for full street scans

            connector = aiohttp.TCPConnector(limit=20)
            async with aiohttp.ClientSession(connector=connector) as session:
                with tqdm(streets, desc="Fetching records", unit="streets") as pbar:
                    for i, street in enumerate(pbar):
                        records = await self._fetch_records_for_street(session, semaphore, street)

                        # Deduplicate
                        new_records = 0
                        for r in records:
                            if r.tik_number not in seen_tiks:
                                seen_tiks.add(r.tik_number)
                                all_records.append(r)
                                new_records += 1

                        pbar.set_postfix(records=len(all_records), street=street['name'][:12])

                        # Save checkpoint every 10 streets
                        if (i + 1) % 10 == 0:
                            logger.debug(f"Saving checkpoint at street {i+1}")
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

        logger.info(f"Fetched {len(all_records)} unique building records. Saved to {self.records_file}")
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
        if resume and self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'details' in data:
                        completed = {d['tik_number']: BuildingDetail(**d) for d in data['details']}
                        logger.info(f"Loaded {len(completed)} records from checkpoint")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")

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

            # Split tik numbers into chunks for each worker
            chunk_size = max(1, len(remaining) // self.workers)
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
                with tqdm(total=len(remaining), desc="Fetching details", unit="buildings") as pbar:
                    for result in pool.imap_unordered(_worker_fetch_details, worker_args):
                        # Merge results
                        for d in result:
                            detail = BuildingDetail(**d)
                            completed[d['tik_number']] = detail
                            if d['fetch_status'] == 'success':
                                total_success += 1
                            else:
                                total_errors += 1
                        pbar.update(len(result))
                        pbar.set_postfix(ok=total_success, err=total_errors)

            elapsed = time.time() - start_time
            logger.info(f"All workers completed in {elapsed:.1f}s. Total details fetched: {len(remaining)}")

        else:
            # Single-process mode: original async implementation
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
            async with aiohttp.ClientSession(connector=connector) as session:
                batch_size = SAVE_INTERVAL

                with tqdm(total=len(remaining), desc="Fetching details", unit="buildings") as pbar:
                    for batch_idx in range(0, len(remaining), batch_size):
                        batch = remaining[batch_idx:batch_idx + batch_size]
                        batch_start = time.time()

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

                        pbar.update(len(batch))
                        pbar.set_postfix(ok=total_success, err=total_errors)

                        # Save checkpoint
                        logger.debug(f"Saving checkpoint with {len(completed)} records")
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

            chunk_size = max(1, len(failed_tiks) // self.workers)
            tik_chunks = []
            for i in range(0, len(failed_tiks), chunk_size):
                chunk = failed_tiks[i:i + chunk_size]
                if chunk:
                    tik_chunks.append(chunk)

            config_dict = asdict(self.config)
            worker_args = [(config_dict, chunk, i) for i, chunk in enumerate(tik_chunks)]

            with multiprocessing.Pool(self.workers) as pool:
                with tqdm(total=len(failed_tiks), desc="Retrying failed", unit="buildings") as pbar:
                    for result in pool.imap_unordered(_worker_fetch_details, worker_args):
                        for d in result:
                            detail = BuildingDetail(**d)
                            all_details[d['tik_number']] = detail
                            if d['fetch_status'] == 'success':
                                total_success += 1
                            else:
                                total_errors += 1
                        pbar.update(len(result))
                        pbar.set_postfix(ok=total_success, err=total_errors)

        else:
            # Single-process mode
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)
            connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

            async with aiohttp.ClientSession(connector=connector) as session:
                batch_size = SAVE_INTERVAL

                with tqdm(total=len(failed_tiks), desc="Retrying failed", unit="buildings") as pbar:
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

                        pbar.update(len(batch))
                        pbar.set_postfix(ok=total_success, err=total_errors)

        # Save updated results
        details_list = list(all_details.values())
        output = {
            "city": self.config.name,
            "city_en": self.config.name_en,
            "fetched_at": datetime.now().isoformat(),
            "total_records": len(details_list),
            "success_count": sum(1 for d in details_list if d.fetch_status == 'success'),
            "error_count": sum(1 for d in details_list if d.fetch_status == 'error'),
            "records": [asdict(d) for d in details_list]
        }

        with open(self.details_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        elapsed = time.time() - start_time
        logger.info(f"Retry complete in {elapsed:.1f}s. Retried {len(failed_tiks)}: {total_success} ok, {total_errors} still failing")
        logger.info(f"Total: {output['success_count']} ok, {output['error_count']} errors. Saved to {self.details_file}")

        return details_list

    async def _fetch_bakasha_details_authenticated(self, records: list[BuildingRecord], resume: bool = True) -> list[BuildingDetail]:
        """Fetch bakasha details using authenticated API"""
        tik_numbers = list(set(r.tik_number for r in records))

        # Load checkpoint if resuming
        completed = {}
        if resume and self.checkpoint_file.exists():
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'details' in data:
                        completed = {d['tik_number']: BuildingDetail(**d) for d in data['details']}
                        logger.info(f"Loaded {len(completed)} records from checkpoint")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint: {e}")

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

            for batch_idx in range(0, len(remaining), batch_size):
                batch = remaining[batch_idx:batch_idx + batch_size]
                batch_start = time.time()

                tasks = [
                    self._fetch_single_bakasha_detail(session, semaphore, tik, self.israeli_id)
                    for tik in batch
                ]
                results = await asyncio.gather(*tasks)

                for result in results:
                    completed[result.tik_number] = result

                processed = batch_idx + len(batch)
                elapsed = time.time() - start_time
                batch_elapsed = time.time() - batch_start
                rate = processed / elapsed if elapsed > 0 else 0
                batch_rate = len(batch) / batch_elapsed if batch_elapsed > 0 else 0
                eta = (len(remaining) - processed) / rate if rate > 0 else 0

                success = sum(1 for r in results if r.fetch_status == 'success')
                errors = sum(1 for r in results if r.fetch_status == 'error')
                total_success += success
                total_errors += errors

                # Log any errors in this batch
                for r in results:
                    if r.fetch_status == 'error':
                        logger.debug(f"Error fetching request {r.tik_number}: {r.fetch_error}")

                logger.info(
                    f"Details: {processed}/{len(remaining)} ({100*processed/len(remaining):.1f}%) | "
                    f"Rate: {rate:.1f}/sec (batch: {batch_rate:.1f}/sec) | "
                    f"ETA: {eta/60:.1f}min | Batch: {success} ok, {errors} err"
                )

                # Save checkpoint
                logger.debug(f"Saving checkpoint with {len(completed)} records")
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

        logger.info(f"Fetched {len(all_details)} bakasha details ({total_success} ok, {total_errors} errors). Saved to {self.details_file}")
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

        logger.info(f"Exported CSV files: {csv_file}, {permits_file}")

    async def run_full_crawl(self, streets_only: bool = False, skip_details: bool = False, force: bool = False, verbose: bool = False, retry_errors: bool = False):
        """Run the complete crawl process"""
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
                self.export_csv(details)
            logger.info("#" * 60)
            logger.info("RETRY COMPLETE")
            logger.info("#" * 60)
            return

        # Step 1: Discover streets (returns all_streets and new_streets)
        all_streets, new_streets = await self.discover_streets(force=force)

        if streets_only:
            logger.info("Streets-only mode. Stopping here.")
            return

        # Step 2: Fetch building records
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
        details = await self.fetch_building_details(records)

        # Step 4: Export CSV
        self.export_csv(details)

        logger.info("#" * 60)
        logger.info("CRAWL COMPLETE")
        logger.info("#" * 60)
        logger.info(f"City: {self.config.name}")
        logger.info(f"Streets: {len(all_streets)}")
        logger.info(f"New Streets: {len(new_streets)}")
        logger.info(f"Building Records: {len(records)}")
        logger.info(f"Building Details: {len(details)}")
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
    parser.add_argument("--skip-details", action="store_true", help="Skip detailed info fetch")
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
        force=args.force,
        verbose=args.verbose,
        retry_errors=args.retry_errors
    ))


if __name__ == "__main__":
    main()
