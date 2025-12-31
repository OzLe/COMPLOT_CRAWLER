"""
Base parser utilities for HTML parsing.

Provides common helper methods used across all parsers.
"""

from typing import Optional
from bs4 import BeautifulSoup, Tag


class BaseParser:
    """Base class with common parsing utilities."""

    @staticmethod
    def get_text_safe(element: Optional[Tag], default: str = "") -> str:
        """Safely extract text from an element."""
        if element is None:
            return default
        return element.get_text(strip=True)

    @staticmethod
    def get_cell_text(cells: list, index: int, default: str = "") -> str:
        """Safely get text from a table cell by index."""
        if index < len(cells):
            return cells[index].get_text(strip=True)
        return default

    @staticmethod
    def has_no_data(soup: BeautifulSoup) -> bool:
        """Check if the response indicates no data available."""
        text = soup.get_text()
        return (
            'לא ניתן להציג את המידע המבוקש' in text or
            'לא אותרו תוצאות' in text
        )

    @staticmethod
    def requires_auth(soup: BeautifulSoup) -> bool:
        """Check if the response requires authentication."""
        text = soup.get_text()
        return (
            'מספר תעודת הזהות' in text or
            'אנא הזינו' in text
        )

    @staticmethod
    def extract_header_field(soup: BeautifulSoup, field_name: str) -> str:
        """Extract a field value from the header section."""
        header_divs = soup.select('#result-title-div-id .top-navbar-info-desc')
        for i, div in enumerate(header_divs):
            if field_name in div.get_text():
                if i + 1 < len(header_divs):
                    return header_divs[i + 1].get_text(strip=True)
        return ""

    @staticmethod
    def extract_table_rows(soup: BeautifulSoup, table_selector: str) -> list:
        """Extract all tbody rows from a table."""
        table = soup.select_one(table_selector)
        if table:
            return table.select('tbody tr')
        return []

    @staticmethod
    def extract_info_table_value(soup: BeautifulSoup, table_selector: str, label: str) -> str:
        """Extract a value from an info table by label."""
        table = soup.select_one(table_selector)
        if table:
            for row in table.select('tr'):
                cells = row.select('td')
                if len(cells) >= 2:
                    if label in cells[0].get_text(strip=True):
                        return cells[1].get_text(strip=True)
        return ""
