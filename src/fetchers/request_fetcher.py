"""
Request detail fetcher.

Fetches detailed permit request information from GetBakashaFile API.
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Tuple

import aiohttp

from src.config import CityConfig
from src.fetchers.base import (
    BaseFetcher, build_url,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, MAX_CONCURRENT
)
from src.parsers.request_parser import parse_request_detail


class RequestFetcher(BaseFetcher):
    """Fetcher for permit request details."""

    async def fetch_request(
        self,
        session: aiohttp.ClientSession,
        request_number: str,
        tik_number: str = "",
        retry: int = 0
    ) -> Dict:
        """
        Fetch details for a single permit request.

        Args:
            session: aiohttp session
            request_number: Permit request number
            tik_number: Associated building file number
            retry: Current retry count

        Returns:
            Request detail dict
        """
        url = build_url(
            "GetBakashaFile",
            siteid=self.config.site_id,
            b=request_number,
            arguments="siteid,b"
        )

        try:
            async with session.get(
                url,
                headers=self.get_headers(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    return parse_request_detail(html, request_number, tik_number)
                else:
                    return self._error_result(request_number, tik_number, f"HTTP {resp.status}")

        except asyncio.TimeoutError:
            if retry < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                return await self.fetch_request(session, request_number, tik_number, retry + 1)
            return self._error_result(request_number, tik_number, "Timeout")

        except Exception as e:
            if retry < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** retry))
                return await self.fetch_request(session, request_number, tik_number, retry + 1)
            return self._error_result(request_number, tik_number, str(e))

    async def fetch_all_requests(
        self,
        session: aiohttp.ClientSession,
        request_items: List[Tuple[str, str]],
        semaphore: asyncio.Semaphore = None
    ) -> List[Dict]:
        """
        Fetch details for multiple requests.

        Args:
            session: aiohttp session
            request_items: List of (request_number, tik_number) tuples
            semaphore: Optional semaphore for concurrency control

        Returns:
            List of request detail dicts
        """
        if semaphore is None:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def fetch_with_semaphore(req_num: str, tik_num: str):
            async with semaphore:
                return await self.fetch_request(session, req_num, tik_num)

        tasks = [fetch_with_semaphore(req_num, tik_num) for req_num, tik_num in request_items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        details = []
        for result in results:
            if isinstance(result, dict):
                details.append(result)

        return details

    def _error_result(self, request_number: str, tik_number: str, error: str) -> Dict:
        """Create an error result dict."""
        return {
            "request_number": request_number,
            "tik_number": tik_number,
            "address": "",
            "submission_date": "",
            "request_type": "",
            "primary_use": "",
            "description": "",
            "permit_number": "",
            "permit_date": "",
            "main_area_sqm": "",
            "service_area_sqm": "",
            "housing_units": "",
            "stakeholders": [],
            "events": [],
            "requirements": [],
            "meetings": [],
            "documents": [],
            "gush_helka": [],
            "fetch_status": "error",
            "fetch_error": error,
            "fetched_at": datetime.now().isoformat()
        }


# Standalone function for multiprocessing workers

async def async_fetch_request_detail(
    session: aiohttp.ClientSession,
    config_dict: dict,
    request_number: str,
    tik_number: str = ""
) -> dict:
    """
    Fetch request detail (standalone function for workers).

    Args:
        session: aiohttp session
        config_dict: City config as dictionary
        request_number: Permit request number
        tik_number: Associated building file number

    Returns:
        Request detail dict
    """
    url = build_url(
        "GetBakashaFile",
        siteid=config_dict['site_id'],
        b=request_number,
        arguments="siteid,b"
    )

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
                return parse_request_detail(html, request_number, tik_number)

        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                return {
                    "request_number": request_number,
                    "tik_number": tik_number,
                    "fetch_status": "error",
                    "fetch_error": str(e),
                    "fetched_at": datetime.now().isoformat(),
                    "address": "", "submission_date": "", "request_type": "",
                    "primary_use": "", "description": "", "permit_number": "",
                    "permit_date": "", "main_area_sqm": "", "service_area_sqm": "",
                    "housing_units": "", "stakeholders": [], "events": [],
                    "requirements": [], "meetings": [], "documents": [], "gush_helka": []
                }
            await asyncio.sleep(RETRY_DELAY)

    return {
        "request_number": request_number,
        "tik_number": tik_number,
        "fetch_status": "error",
        "fetch_error": "Max retries exceeded",
        "fetched_at": datetime.now().isoformat(),
        "address": "", "submission_date": "", "request_type": "",
        "primary_use": "", "description": "", "permit_number": "",
        "permit_date": "", "main_area_sqm": "", "service_area_sqm": "",
        "housing_units": "", "stakeholders": [], "events": [],
        "requirements": [], "meetings": [], "documents": [], "gush_helka": []
    }


async def async_fetch_requests_batch(
    config_dict: dict,
    request_items: List[Tuple[str, str]]
) -> List[dict]:
    """
    Fetch request details for a batch (standalone function for workers).

    Args:
        config_dict: City config as dictionary
        request_items: List of (request_number, tik_number) tuples

    Returns:
        List of request detail dicts
    """
    results = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def fetch_with_semaphore(session, req_num, tik_num):
        async with semaphore:
            return await async_fetch_request_detail(session, config_dict, req_num, tik_num)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [fetch_with_semaphore(session, req_num, tik_num) for req_num, tik_num in request_items]

        batch_size = 100
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            for result in batch_results:
                if isinstance(result, dict):
                    results.append(result)

    return results
