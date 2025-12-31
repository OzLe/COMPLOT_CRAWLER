"""
Street discovery fetcher.

Discovers valid street codes by testing address queries.
"""

import asyncio
from typing import Optional, List, Dict

import aiohttp
from bs4 import BeautifulSoup

from src.config import CityConfig
from src.fetchers.base import (
    BaseFetcher, build_url,
    REQUEST_TIMEOUT, MAX_CONCURRENT
)


class StreetFetcher(BaseFetcher):
    """Fetcher for discovering valid street codes."""

    # House numbers to try when testing a street
    TEST_HOUSE_NUMBERS = [1, 2, 3, 5, 10, 20, 50]

    async def test_street(
        self,
        session: aiohttp.ClientSession,
        street_code: int
    ) -> Optional[Dict]:
        """
        Test if a street code is valid.

        Args:
            session: aiohttp session
            street_code: Street code to test

        Returns:
            Dict with 'code' and 'name' if valid, None otherwise
        """
        for h in self.TEST_HOUSE_NUMBERS:
            url = self._build_search_url(street_code, h)

            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                ) as resp:
                    if resp.status != 200:
                        continue

                    html = await resp.text()
                    street_name = self._extract_street_name(html)
                    if street_name:
                        return {"code": street_code, "name": street_name}

            except Exception:
                continue

        return None

    def _build_search_url(self, street_code: int, house_num: int) -> str:
        """Build URL for address search."""
        if self.config.api_type == "tikim":
            return build_url(
                "GetTikimByAddress",
                siteid=self.config.site_id,
                c=self.config.city_code,
                s=street_code,
                h=house_num,
                l="true",
                arguments="siteid,c,s,h,l"
            )
        else:  # bakashot
            return build_url(
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

    def _extract_street_name(self, html: str) -> Optional[str]:
        """Extract street name from search results."""
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()

        if "נמצאו" not in text:
            return None
        if "תיקי בניין" not in text and "בקשות" not in text:
            return None

        table = soup.find("table", {"id": "results-table"})
        if not table:
            return None

        rows = table.select("tbody tr")
        if not rows:
            return None

        cells = rows[0].find_all("td")
        for cell in cells:
            cell_text = cell.get_text(strip=True)
            if self.config.name in cell_text:
                # Extract street name by removing city and house number
                parts = cell_text.replace(self.config.name, '').strip().rsplit(' ', 1)
                street_name = parts[0].strip() if parts else cell_text
                if street_name and len(street_name) > 1:
                    return street_name

        return None

    async def discover_streets(
        self,
        session: aiohttp.ClientSession,
        start: int,
        end: int,
        semaphore: asyncio.Semaphore = None
    ) -> List[Dict]:
        """
        Discover all valid streets in a range.

        Args:
            session: aiohttp session
            start: Start of street code range
            end: End of street code range
            semaphore: Optional semaphore for concurrency control

        Returns:
            List of valid street dicts with 'code' and 'name'
        """
        if semaphore is None:
            semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        streets = []

        async def test_with_semaphore(street_code: int):
            async with semaphore:
                return await self.test_street(session, street_code)

        tasks = [test_with_semaphore(s) for s in range(start, end + 1)]

        # Process in batches
        batch_size = 100
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    streets.append(result)

        return streets


# Standalone functions for multiprocessing workers

async def async_test_street(
    session: aiohttp.ClientSession,
    config_dict: dict,
    street_code: int
) -> Optional[dict]:
    """
    Test if a street code is valid (standalone function for workers).

    Args:
        session: aiohttp session
        config_dict: City config as dictionary
        street_code: Street code to test

    Returns:
        Dict with 'code' and 'name' if valid, None otherwise
    """
    house_numbers = [1, 2, 3, 5, 10, 20, 50]
    city_name = config_dict['name']

    for h in house_numbers:
        if config_dict['api_type'] == "tikim":
            url = build_url(
                "GetTikimByAddress",
                siteid=config_dict['site_id'],
                c=config_dict['city_code'],
                s=street_code,
                h=h,
                l="true",
                arguments="siteid,c,s,h,l"
            )
        else:
            url = build_url(
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
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as resp:
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
                            for cell in cells:
                                cell_text = cell.get_text(strip=True)
                                if city_name in cell_text:
                                    parts = cell_text.replace(city_name, '').strip().rsplit(' ', 1)
                                    street_name = parts[0].strip() if parts else cell_text
                                    if street_name and len(street_name) > 1:
                                        return {"code": street_code, "name": street_name}
        except Exception:
            continue

    return None


async def async_discover_range(
    config_dict: dict,
    start: int,
    end: int
) -> List[dict]:
    """
    Discover streets in a range (standalone function for workers).

    Args:
        config_dict: City config as dictionary
        start: Start of street code range
        end: End of street code range

    Returns:
        List of valid street dicts
    """
    streets = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def test_with_semaphore(session, street_code):
        async with semaphore:
            return await async_test_street(session, config_dict, street_code)

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
