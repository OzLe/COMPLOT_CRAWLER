"""
Search result HTML parser.

Parses HTML responses from GetTikimByAddress and GetBakashotByAddress APIs
to extract building records and street information.
"""

import re
from typing import Optional
from bs4 import BeautifulSoup

from src.parsers.base import BaseParser


class SearchResultParser(BaseParser):
    """Parser for search result HTML responses."""

    def has_results(self, soup: BeautifulSoup) -> bool:
        """Check if the response contains valid results."""
        text = soup.get_text()
        return "נמצאו" in text and ("תיקי בניין" in text or "בקשות" in text)

    def has_no_results(self, soup: BeautifulSoup) -> bool:
        """Check if the response indicates no results found."""
        text = soup.get_text()
        return "לא אותרו" in text or "לא ניתן" in text

    def extract_street_name(self, html: str, city_name: str) -> Optional[str]:
        """
        Extract street name from search results.

        Args:
            html: Raw HTML response
            city_name: The city name to look for in addresses

        Returns:
            Street name or None if not found
        """
        soup = BeautifulSoup(html, 'html.parser')

        if not self.has_results(soup):
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
            if city_name in cell_text:
                # Extract street name by removing city and house number
                parts = cell_text.replace(city_name, '').strip().rsplit(' ', 1)
                street_name = parts[0].strip() if parts else cell_text
                if street_name and len(street_name) > 1:
                    return street_name

        return None

    def parse_building_records(self, html: str, city_name: str, street_code: int,
                                street_name: str, house_number: int) -> list:
        """
        Parse building records from search results.

        Args:
            html: Raw HTML response from GetTikimByAddress
            city_name: City name for address matching
            street_code: Street code used in query
            street_name: Street name
            house_number: House number used in query

        Returns:
            List of building record dictionaries
        """
        soup = BeautifulSoup(html, 'html.parser')
        records = []

        if self.has_no_results(soup):
            return records

        table = soup.find("table", {"id": "results-table"})
        if not table:
            return records

        rows = table.select("tbody tr")
        for row in rows:
            record = self._parse_building_row(row, city_name, street_code,
                                               street_name, house_number)
            if record:
                records.append(record)

        return records

    def _parse_building_row(self, row, city_name: str, street_code: int,
                            street_name: str, house_number: int) -> Optional[dict]:
        """Parse a single row from building results table."""
        cells = row.find_all("td")
        if len(cells) < 3:
            return None

        # Extract tik number from link
        tik = self._extract_tik_number(row)
        if not tik:
            return None

        # Get address from cell containing city name
        address = ""
        for cell in cells:
            text = cell.get_text(strip=True)
            if city_name in text:
                address = text
                break

        # Get gush/helka from numeric cells at the end
        gush, helka = self._extract_gush_helka(cells)

        return {
            "tik_number": tik,
            "address": address,
            "gush": gush,
            "helka": helka,
            "migrash": "",
            "street_code": street_code,
            "street_name": street_name,
            "house_number": house_number
        }

    def _extract_tik_number(self, row) -> Optional[str]:
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

        # Look for numeric cells from the end
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
