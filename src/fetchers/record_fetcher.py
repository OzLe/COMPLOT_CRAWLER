"""
Building record fetcher.

Fetches building records by address search.
"""

import asyncio
import re
from typing import List, Dict

import aiohttp
from bs4 import BeautifulSoup

from src.config import CityConfig
from src.fetchers.base import (
    BaseFetcher, build_url,
    REQUEST_TIMEOUT, MAX_CONCURRENT
)


class RecordFetcher(BaseFetcher):
    """Fetcher for building records from address searches."""

    async def fetch_records_for_street(
        self,
        session: aiohttp.ClientSession,
        street: Dict,
        max_house_number: int = 500
    ) -> List[Dict]:
        """
        Fetch all building records for a street.

        Args:
            session: aiohttp session
            street: Street dict with 'code' and 'name'
            max_house_number: Maximum house number to try

        Returns:
            List of building record dicts
        """
        records = []
        street_code = street['code']
        street_name = street['name']

        for house_num in range(1, max_house_number):
            url = self._build_search_url(street_code, house_num)

            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
                ) as resp:
                    if resp.status != 200:
                        continue

                    html = await resp.text()
                    page_records = self._parse_records(
                        html, street_code, street_name, house_num
                    )
                    records.extend(page_records)

            except Exception:
                continue

        return records

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
        else:
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

    def _parse_records(
        self,
        html: str,
        street_code: int,
        street_name: str,
        house_num: int
    ) -> List[Dict]:
        """Parse building records from search results."""
        records = []
        soup = BeautifulSoup(html, 'html.parser')

        if "לא אותרו" in soup.get_text() or "לא ניתן" in soup.get_text():
            return records

        table = soup.find("table", {"id": "results-table"})
        if not table:
            return records

        for row in table.select("tbody tr"):
            record = self._parse_row(row, street_code, street_name, house_num)
            if record:
                records.append(record)

        return records

    def _parse_row(
        self,
        row,
        street_code: int,
        street_name: str,
        house_num: int
    ) -> Dict:
        """Parse a single table row into a record."""
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        # Extract tik number
        tik = self._extract_tik_number(row)
        if not tik:
            return None

        # Get address
        address = ""
        for cell in cells:
            text = cell.get_text(strip=True)
            if self.config.name in text:
                address = text
                break

        # Get gush/helka
        gush, helka = self._extract_gush_helka(cells)

        return {
            "tik_number": tik,
            "address": address,
            "gush": gush,
            "helka": helka,
            "migrash": "",
            "street_code": street_code,
            "street_name": street_name,
            "house_number": house_num
        }

    def _extract_tik_number(self, row) -> str:
        """Extract tik number from a table row."""
        # Look for getBuilding link first
        for link in row.find_all("a", href=True):
            href = str(link.get("href", ""))
            if "getBuilding" in href:
                match = re.search(r'getBuilding\((\d+)\)', href)
                if match:
                    return match.group(1)

        # Try first link as fallback
        link = row.find("a", href=True)
        if link:
            text = link.get_text(strip=True)
            if text.isdigit():
                return text
            match = re.search(r'\d+', text)
            if match:
                return match.group()

        return None

    def _extract_gush_helka(self, cells) -> tuple:
        """Extract gush and helka from table cells."""
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

        return gush, helka


# Standalone function for multiprocessing workers

async def async_fetch_records_for_street(
    session: aiohttp.ClientSession,
    config_dict: dict,
    street: dict
) -> List[dict]:
    """
    Fetch all building records for a street (standalone function for workers).

    Args:
        session: aiohttp session
        config_dict: City config as dictionary
        street: Street dict with 'code' and 'name'

    Returns:
        List of building record dicts
    """
    records = []
    street_code = street['code']
    street_name = street['name']
    city_name = config_dict['name']
    consecutive_empty = 0
    max_consecutive_empty = 30  # Stop after 30 consecutive empty results

    for house_num in range(1, 500):
        if config_dict['api_type'] == "tikim":
            url = build_url(
                "GetTikimByAddress",
                siteid=config_dict['site_id'],
                c=config_dict['city_code'],
                s=street_code,
                h=house_num,
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
                h=house_num,
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

                if "לא אותרו" in soup.get_text() or "לא ניתן" in soup.get_text():
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        break  # Early exit - no more results expected
                    continue

                table = soup.find("table", {"id": "results-table"})
                if not table:
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        break
                    continue

                rows = table.select("tbody tr")
                if not rows:
                    consecutive_empty += 1
                    if consecutive_empty >= max_consecutive_empty:
                        break
                    continue

                # Found results - reset counter
                consecutive_empty = 0
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue

                    # Extract tik number
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

                    # Get address
                    address = ""
                    for cell in cells:
                        text = cell.get_text(strip=True)
                        if city_name in text:
                            address = text
                            break

                    # Get gush/helka
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
