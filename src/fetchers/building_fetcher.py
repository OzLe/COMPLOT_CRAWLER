"""
Building detail fetcher.

Fetches detailed building information from GetTikFile API.
"""

import asyncio
from datetime import datetime
from typing import Dict, List

import aiohttp

from src.config import CityConfig
from src.fetchers.base import (
    BaseFetcher, build_url,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, MAX_CONCURRENT
)
from src.parsers.building_parser import parse_building_detail


class BuildingFetcher(BaseFetcher):
    """Fetcher for building detail information."""

    async def fetch_detail(
        self,
        session: aiohttp.ClientSession,
        tik_number: str,
        retry: int = 0
    ) -> Dict:
        """
        Fetch details for a single building.

        Args:
            session: aiohttp session
            tik_number: Building file number
            retry: Current retry count

        Returns:
            Building detail dict
        """
        url = build_url(
            "GetTikFile",
            siteid=self.config.site_id,
            t=tik_number,
            arguments="siteid,t"
        )

        try:
            async with session.get(
                url,
                headers=self.get_headers(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    return parse_building_detail(html, tik_number)
                else:
                    return self._error_result(tik_number, f"HTTP {resp.status}")

        except asyncio.TimeoutError:
            if retry < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                return await self.fetch_detail(session, tik_number, retry + 1)
            return self._error_result(tik_number, "Timeout")

        except Exception as e:
            if retry < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                return await self.fetch_detail(session, tik_number, retry + 1)
            return self._error_result(tik_number, str(e))

    async def fetch_all_details(
        self,
        session: aiohttp.ClientSession,
        tik_numbers: List[str],
        semaphore: asyncio.Semaphore = None
    ) -> List[Dict]:
        """
        Fetch details for multiple buildings.

        Args:
            session: aiohttp session
            tik_numbers: List of building file numbers
            semaphore: Optional semaphore for concurrency control

        Returns:
            List of building detail dicts
        """
        if semaphore is None:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def fetch_with_semaphore(tik: str):
            async with semaphore:
                return await self.fetch_detail(session, tik)

        tasks = [fetch_with_semaphore(tik) for tik in tik_numbers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        details = []
        for result in results:
            if isinstance(result, dict):
                details.append(result)
            elif isinstance(result, Exception):
                pass  # Skip exceptions

        return details

    def _error_result(self, tik_number: str, error: str) -> Dict:
        """Create an error result dict."""
        return {
            "tik_number": tik_number,
            "address": "",
            "neighborhood": "",
            "addresses": [],
            "gush_helka": [],
            "plans": [],
            "requests": [],
            "stakeholders": [],
            "documents": [],
            "fetch_status": "error",
            "fetch_error": error,
            "fetched_at": datetime.now().isoformat()
        }


# Standalone function for multiprocessing workers

async def async_fetch_building_detail(
    session: aiohttp.ClientSession,
    config_dict: dict,
    tik_number: str,
    retry: int = 0
) -> dict:
    """
    Fetch building detail (standalone function for workers).

    Args:
        session: aiohttp session
        config_dict: City config as dictionary
        tik_number: Building file number
        retry: Current retry count

    Returns:
        Building detail dict
    """
    url = build_url(
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
        async with session.get(
            url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        ) as resp:
            if resp.status == 200:
                html = await resp.text()
                return parse_building_detail(html, tik_number)
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
            return await async_fetch_building_detail(session, config_dict, tik_number, retry + 1)
        return {
            "tik_number": tik_number,
            "fetch_status": "error",
            "fetch_error": "Timeout",
            "fetched_at": datetime.now().isoformat()
        }

    except Exception as e:
        if retry < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY * (2 ** retry))
            return await async_fetch_building_detail(session, config_dict, tik_number, retry + 1)
        return {
            "tik_number": tik_number,
            "fetch_status": "error",
            "fetch_error": str(e),
            "fetched_at": datetime.now().isoformat()
        }


async def async_fetch_details_batch(
    config_dict: dict,
    tik_numbers: List[str]
) -> List[dict]:
    """
    Fetch building details for a batch (standalone function for workers).

    Args:
        config_dict: City config as dictionary
        tik_numbers: List of building file numbers

    Returns:
        List of building detail dicts
    """
    details = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def fetch_with_semaphore(session, tik):
        async with semaphore:
            return await async_fetch_building_detail(session, config_dict, tik)

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

    return details
