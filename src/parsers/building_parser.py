"""
Building detail HTML parser.

Parses HTML responses from GetTikFile API to extract building information.
"""

from datetime import datetime
from typing import Union
from bs4 import BeautifulSoup

from src.models import BuildingDetail
from src.parsers.base import BaseParser


class BuildingDetailParser(BaseParser):
    """Parser for building detail HTML responses (GetTikFile API)."""

    def parse(self, html: str, tik_number: str) -> BuildingDetail:
        """
        Parse building detail HTML and return a BuildingDetail object.

        Args:
            html: Raw HTML response from GetTikFile API
            tik_number: The building file number

        Returns:
            BuildingDetail with parsed data and fetch status
        """
        soup = BeautifulSoup(html, 'html.parser')
        detail = BuildingDetail(tik_number=tik_number)
        detail.fetched_at = datetime.now().isoformat()

        # Check for error responses
        if self.has_no_data(soup):
            detail.fetch_status = "error"
            detail.fetch_error = "No data available"
            return detail

        # Extract all sections
        detail.address = self._extract_address(soup)
        detail.neighborhood = self._extract_neighborhood(soup)
        detail.addresses = self._extract_addresses(soup)
        detail.gush_helka = self._extract_gush_helka(soup)
        detail.requests = self._extract_requests(soup)
        detail.plans = self._extract_plans(soup)
        detail.stakeholders = self._extract_stakeholders(soup)
        detail.documents = self._extract_documents(soup)

        detail.fetch_status = "success"
        return detail

    def parse_to_dict(self, html: str, tik_number: str) -> dict:
        """
        Parse building detail HTML and return a dictionary.

        This is used by multiprocessing workers that need picklable results.
        """
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

        # Check for error responses
        if self.has_no_data(soup):
            detail["fetch_status"] = "error"
            detail["fetch_error"] = "No data available"
            return detail

        # Extract all sections
        detail["address"] = self._extract_address(soup)
        detail["neighborhood"] = self._extract_neighborhood(soup)
        detail["addresses"] = self._extract_addresses(soup)
        detail["gush_helka"] = self._extract_gush_helka(soup)
        detail["requests"] = self._extract_requests(soup)
        detail["plans"] = self._extract_plans(soup)

        detail["fetch_status"] = "success"
        return detail

    def _extract_address(self, soup: BeautifulSoup) -> str:
        """Extract main address from header."""
        return self.extract_header_field(soup, 'כתובת')

    def _extract_neighborhood(self, soup: BeautifulSoup) -> str:
        """Extract neighborhood from info table."""
        return self.extract_info_table_value(soup, '#info-main', 'שכונה')

    def _extract_addresses(self, soup: BeautifulSoup) -> list:
        """Extract all addresses from addresses table."""
        addresses = []
        addresses_div = soup.select_one('#addresses')
        if addresses_div:
            for row in addresses_div.select('tbody tr'):
                addr = row.get_text(strip=True)
                if addr:
                    addresses.append(addr)
        return addresses

    def _extract_gush_helka(self, soup: BeautifulSoup) -> list:
        """Extract parcel (gush/helka) information."""
        parcels = []
        rows = self.extract_table_rows(soup, '#table-gushim-helkot')
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 5:
                gush_info = {
                    'gush': self.get_cell_text(cells, 1),
                    'helka': self.get_cell_text(cells, 2),
                    'migrash': self.get_cell_text(cells, 3),
                    'plan_number': self.get_cell_text(cells, 4)
                }
                if gush_info['gush']:
                    parcels.append(gush_info)
        return parcels

    def _extract_requests(self, soup: BeautifulSoup) -> list:
        """Extract permit requests from requests table."""
        requests = []
        rows = self.extract_table_rows(soup, '#table-requests')
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 7:
                request_info = {
                    'request_number': self.get_cell_text(cells, 1),
                    'submission_date': self.get_cell_text(cells, 2),
                    'last_event': self.get_cell_text(cells, 3),
                    'applicant_name': self.get_cell_text(cells, 4),
                    'permit_number': self.get_cell_text(cells, 5),
                    'permit_date': self.get_cell_text(cells, 6)
                }
                if request_info['request_number']:
                    requests.append(request_info)
        return requests

    def _extract_plans(self, soup: BeautifulSoup) -> list:
        """Extract urban plans from plans table."""
        plans = []
        rows = self.extract_table_rows(soup, '#table-taba')
        for row in rows:
            if 'לא אותרו' in row.get_text():
                continue
            cells = row.select('td')
            if len(cells) >= 5:
                plan_info = {
                    'plan_number': self.get_cell_text(cells, 1),
                    'plan_name': self.get_cell_text(cells, 2),
                    'status': self.get_cell_text(cells, 3),
                    'status_date': self.get_cell_text(cells, 4)
                }
                if plan_info['plan_number']:
                    plans.append(plan_info)
        return plans

    def _extract_stakeholders(self, soup: BeautifulSoup) -> list:
        """Extract stakeholders list."""
        stakeholders = []
        stakeholders_div = soup.select_one('#baaley-inyan')
        if stakeholders_div:
            for row in stakeholders_div.select('tr'):
                text = row.get_text(strip=True)
                if text and 'לא נמצאו נתונים' not in text:
                    stakeholders.append(text)
        return stakeholders

    def _extract_documents(self, soup: BeautifulSoup) -> list:
        """Extract archive documents."""
        documents = []
        rows = self.extract_table_rows(soup, '#table-archive')
        for row in rows:
            if 'לא נמצאו מסמכים' in row.get_text():
                continue
            cells = row.select('td')
            if len(cells) >= 3:
                doc_info = {
                    'name': self.get_cell_text(cells, 0),
                    'subject': self.get_cell_text(cells, 1),
                    'date': self.get_cell_text(cells, 2)
                }
                if doc_info['name']:
                    documents.append(doc_info)
        return documents


# Standalone function for backward compatibility with multiprocessing workers
def parse_building_detail(html: str, tik_number: str) -> dict:
    """
    Parse building detail HTML (standalone function for workers).

    This function is used by multiprocessing workers that need
    a module-level function for pickling.
    """
    parser = BuildingDetailParser()
    return parser.parse_to_dict(html, tik_number)
