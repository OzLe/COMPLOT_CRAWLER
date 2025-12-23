#!/usr/bin/env python3
"""
Optimized async fetcher for building permit details from Ofaqim municipality.
Uses aiohttp for parallel HTTP requests with rate limiting.
"""

import asyncio
import aiohttp
import json
import re
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

# Configuration
SITE_ID = 67  # Ofaqim municipality
API_URL = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
MAX_CONCURRENT_REQUESTS = 20  # Balance between speed and server load
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2  # Base delay for exponential backoff
SAVE_INTERVAL = 100  # Save progress every N records
OUTPUT_FILE = "building_details.json"
CHECKPOINT_FILE = "building_details_checkpoint.json"


@dataclass
class RequestInfo:
    """Represents a building permit request (בקשה)"""
    request_number: str = ""
    submission_date: str = ""
    last_event: str = ""
    applicant_name: str = ""
    permit_number: str = ""
    permit_date: str = ""


@dataclass
class GushHelkaInfo:
    """Represents parcel information"""
    gush: str = ""
    helka: str = ""
    migrash: str = ""
    plan_number: str = ""


@dataclass
class BuildingDetail:
    """Complete building file details"""
    tik_number: str
    address: str = ""
    neighborhood: str = ""
    addresses: List[str] = field(default_factory=list)
    gush_helka: List[Dict] = field(default_factory=list)
    plans: List[Dict] = field(default_factory=list)
    requests: List[Dict] = field(default_factory=list)
    stakeholders: List[str] = field(default_factory=list)
    documents: List[Dict] = field(default_factory=list)
    fetch_status: str = "pending"
    fetch_error: str = ""
    fetched_at: str = ""


def parse_building_html(html: str, tik_number: str) -> BuildingDetail:
    """Parse the HTML response and extract building details"""
    soup = BeautifulSoup(html, 'html.parser')
    detail = BuildingDetail(tik_number=tik_number)
    detail.fetched_at = datetime.now().isoformat()

    # Extract address from header
    header_divs = soup.select('#result-title-div-id .top-navbar-info-desc')
    for i, div in enumerate(header_divs):
        if 'כתובת' in div.get_text():
            if i + 1 < len(header_divs):
                detail.address = header_divs[i + 1].get_text(strip=True)

    # Extract general info (neighborhood)
    info_main = soup.select_one('#info-main')
    if info_main:
        for row in info_main.select('tr'):
            cells = row.select('td')
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if 'שכונה' in label:
                    detail.neighborhood = value

    # Extract stakeholders (בעלי עניין)
    stakeholders_div = soup.select_one('#baaley-inyan')
    if stakeholders_div:
        for row in stakeholders_div.select('tr'):
            text = row.get_text(strip=True)
            if text and 'לא נמצאו נתונים' not in text:
                detail.stakeholders.append(text)

    # Extract addresses
    addresses_div = soup.select_one('#addresses')
    if addresses_div:
        for row in addresses_div.select('tbody tr'):
            addr = row.get_text(strip=True)
            if addr:
                detail.addresses.append(addr)

    # Extract gush/helka information
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
                if gush_info['gush']:  # Only add if gush exists
                    detail.gush_helka.append(gush_info)

    # Extract plans (תוכניות)
    plans_table = soup.select_one('#table-taba')
    if plans_table:
        for row in plans_table.select('tbody tr'):
            cells = row.select('td')
            if len(cells) >= 5 and 'לא אותרו' not in row.get_text():
                plan_info = {
                    'plan_number': cells[1].get_text(strip=True),
                    'plan_name': cells[2].get_text(strip=True),
                    'status': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                    'status_date': cells[4].get_text(strip=True) if len(cells) > 4 else ''
                }
                if plan_info['plan_number']:
                    detail.plans.append(plan_info)

    # Extract requests/permits (בקשות)
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

    # Extract archive documents
    archive_table = soup.select_one('#table-archive')
    if archive_table:
        for row in archive_table.select('tbody tr'):
            cells = row.select('td')
            if len(cells) >= 3 and 'לא נמצאו מסמכים' not in row.get_text():
                doc_info = {
                    'name': cells[0].get_text(strip=True),
                    'subject': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                    'date': cells[2].get_text(strip=True) if len(cells) > 2 else ''
                }
                if doc_info['name']:
                    detail.documents.append(doc_info)

    detail.fetch_status = "success"
    return detail


async def fetch_building_detail(
    session: aiohttp.ClientSession,
    tik_number: str,
    semaphore: asyncio.Semaphore,
    retry_count: int = 0
) -> BuildingDetail:
    """Fetch details for a single building file"""
    async with semaphore:
        params = {
            'appname': 'cixpa',
            'prgname': 'GetTikFile',
            'siteid': SITE_ID,
            't': tik_number,
            'arguments': 'siteid,t'
        }

        try:
            async with session.get(API_URL, params=params, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as response:
                if response.status == 200:
                    html = await response.text()
                    return parse_building_html(html, tik_number)
                else:
                    detail = BuildingDetail(tik_number=tik_number)
                    detail.fetch_status = "error"
                    detail.fetch_error = f"HTTP {response.status}"
                    return detail

        except asyncio.TimeoutError:
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry_count))
                return await fetch_building_detail(session, tik_number, semaphore, retry_count + 1)
            detail = BuildingDetail(tik_number=tik_number)
            detail.fetch_status = "error"
            detail.fetch_error = "Timeout after retries"
            return detail

        except Exception as e:
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry_count))
                return await fetch_building_detail(session, tik_number, semaphore, retry_count + 1)
            detail = BuildingDetail(tik_number=tik_number)
            detail.fetch_status = "error"
            detail.fetch_error = str(e)
            return detail


def load_checkpoint() -> Dict[str, Any]:
    """Load existing checkpoint data if available"""
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'completed': {}, 'last_index': 0}


def save_checkpoint(completed: Dict[str, BuildingDetail], last_index: int):
    """Save progress checkpoint"""
    checkpoint_data = {
        'completed': {k: asdict(v) for k, v in completed.items()},
        'last_index': last_index,
        'saved_at': datetime.now().isoformat()
    }
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)


def save_final_results(results: List[BuildingDetail]):
    """Save final results to JSON file"""
    output = {
        'fetched_at': datetime.now().isoformat(),
        'total_records': len(results),
        'success_count': sum(1 for r in results if r.fetch_status == 'success'),
        'error_count': sum(1 for r in results if r.fetch_status == 'error'),
        'records': [asdict(r) for r in results]
    }
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


async def fetch_all_buildings(tik_numbers: List[str], resume: bool = True):
    """Fetch details for all building files with progress tracking"""

    # Load checkpoint if resuming
    checkpoint = load_checkpoint() if resume else {'completed': {}, 'last_index': 0}
    completed = {k: BuildingDetail(**v) for k, v in checkpoint['completed'].items()}

    # Filter out already completed
    remaining = [t for t in tik_numbers if t not in completed]

    print(f"\n{'='*60}")
    print(f"Building Details Fetcher")
    print(f"{'='*60}")
    print(f"Total records: {len(tik_numbers)}")
    print(f"Already completed: {len(completed)}")
    print(f"Remaining: {len(remaining)}")
    print(f"Concurrent requests: {MAX_CONCURRENT_REQUESTS}")
    print(f"{'='*60}\n")

    if not remaining:
        print("All records already fetched!")
        return list(completed.values())

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    start_time = time.time()
    processed = 0

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS, limit_per_host=MAX_CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(connector=connector) as session:
        # Process in batches for better progress tracking
        batch_size = SAVE_INTERVAL
        total_batches = (len(remaining) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            batch_start = batch_idx * batch_size
            batch_end = min(batch_start + batch_size, len(remaining))
            batch = remaining[batch_start:batch_end]

            # Create tasks for this batch
            tasks = [
                fetch_building_detail(session, tik, semaphore)
                for tik in batch
            ]

            # Process batch
            results = await asyncio.gather(*tasks)

            # Update completed
            for result in results:
                completed[result.tik_number] = result

            processed += len(batch)
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(remaining) - processed) / rate if rate > 0 else 0

            success_count = sum(1 for r in results if r.fetch_status == 'success')
            error_count = sum(1 for r in results if r.fetch_status == 'error')

            print(f"Progress: {processed}/{len(remaining)} ({100*processed/len(remaining):.1f}%) | "
                  f"Rate: {rate:.1f}/sec | ETA: {eta/60:.1f} min | "
                  f"Batch: {success_count} ok, {error_count} errors")

            # Save checkpoint
            save_checkpoint(completed, batch_end)

    # Save final results
    all_results = list(completed.values())
    save_final_results(all_results)

    elapsed = time.time() - start_time
    success_count = sum(1 for r in all_results if r.fetch_status == 'success')
    error_count = sum(1 for r in all_results if r.fetch_status == 'error')

    print(f"\n{'='*60}")
    print(f"Fetch Complete!")
    print(f"{'='*60}")
    print(f"Total time: {elapsed/60:.1f} minutes")
    print(f"Total records: {len(all_results)}")
    print(f"Successful: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Output saved to: {OUTPUT_FILE}")
    print(f"{'='*60}\n")

    return all_results


async def main():
    # Load building records
    input_file = "ofakim_building_records.json"

    print(f"Loading building records from {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    tik_numbers = [r['tik_number'] for r in data['records']]
    print(f"Found {len(tik_numbers)} building records")

    # Fetch all details
    results = await fetch_all_buildings(tik_numbers, resume=True)

    return results


if __name__ == "__main__":
    asyncio.run(main())
