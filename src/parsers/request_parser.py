"""
Permit request detail HTML parser.

Parses HTML responses from GetBakashaFile API to extract detailed permit information.
"""

from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

from src.models import RequestDetail
from src.parsers.base import BaseParser


class RequestDetailParser(BaseParser):
    """Parser for permit request detail HTML responses (GetBakashaFile API)."""

    # Field mapping from Hebrew labels to attribute names
    FIELD_MAP = {
        'מספר תיק בניין': 'tik_number',
        'סוג הבקשה': 'request_type',
        'שימוש עיקרי': 'primary_use',
        'תיאור הבקשה': 'description',
        'מספר היתר': 'permit_number',
        'תאריך הפקת היתר': 'permit_date',
        'שטח עיקרי': 'main_area_sqm',
        'שטח שירות': 'service_area_sqm',
        'סך מספר יחידות דיור': 'housing_units',
    }

    def parse(self, html: str, request_number: str, tik_number: str = "") -> RequestDetail:
        """
        Parse request detail HTML and return a RequestDetail object.

        Args:
            html: Raw HTML response from GetBakashaFile API
            request_number: The permit request number
            tik_number: The associated building file number (optional)

        Returns:
            RequestDetail with parsed data and fetch status
        """
        soup = BeautifulSoup(html, 'html.parser')
        detail = RequestDetail(request_number=request_number, tik_number=tik_number)
        detail.fetched_at = datetime.now().isoformat()

        # Check for error responses
        if self.has_no_data(soup):
            detail.fetch_status = "error"
            detail.fetch_error = "No data available"
            return detail

        # Extract all sections
        self._extract_header_info(soup, detail)
        self._extract_general_info(soup, detail)
        detail.stakeholders = self._extract_stakeholders(soup)
        detail.events = self._extract_events(soup)
        detail.requirements = self._extract_requirements(soup)
        detail.meetings = self._extract_meetings(soup)
        detail.documents = self._extract_documents(soup)
        detail.gush_helka = self._extract_gush_helka(soup)

        detail.fetch_status = "success"
        return detail

    def parse_to_dict(self, html: str, request_number: str, tik_number: str = "") -> dict:
        """
        Parse request detail HTML and return a dictionary.

        This is used by multiprocessing workers that need picklable results.
        """
        soup = BeautifulSoup(html, 'html.parser')
        detail = {
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
            "fetch_status": "pending",
            "fetch_error": "",
            "fetched_at": datetime.now().isoformat()
        }

        # Check for error responses
        if self.has_no_data(soup):
            detail["fetch_status"] = "error"
            detail["fetch_error"] = "No data available"
            return detail

        # Extract header info
        header = soup.select_one('#result-title-div-id')
        if header:
            divs = header.select('.top-navbar-info-desc')
            for i, div in enumerate(divs):
                text_content = div.get_text(strip=True)
                if 'כתובת' in text_content and i + 1 < len(divs):
                    detail["address"] = divs[i + 1].get_text(strip=True)
                elif 'תאריך הגשה' in text_content and i + 1 < len(divs):
                    detail["submission_date"] = divs[i + 1].get_text(strip=True)

        # Extract general info
        info_main = soup.select_one('#info-main')
        if info_main:
            for row in info_main.select('tr'):
                cells = row.select('td')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).rstrip(':')
                    value = cells[1].get_text(strip=True)
                    for hebrew, field_name in self.FIELD_MAP.items():
                        if hebrew in label:
                            detail[field_name] = value
                            break

        # Extract all list sections
        detail["stakeholders"] = self._extract_stakeholders(soup)
        detail["events"] = self._extract_events(soup)
        detail["requirements"] = self._extract_requirements(soup)
        detail["meetings"] = self._extract_meetings(soup)
        detail["documents"] = self._extract_documents(soup)
        detail["gush_helka"] = self._extract_gush_helka(soup)

        detail["fetch_status"] = "success"
        return detail

    def _extract_header_info(self, soup: BeautifulSoup, detail: RequestDetail):
        """Extract address and submission date from header."""
        header = soup.select_one('#result-title-div-id')
        if header:
            divs = header.select('.top-navbar-info-desc')
            for i, div in enumerate(divs):
                text_content = div.get_text(strip=True)
                if 'כתובת' in text_content and i + 1 < len(divs):
                    detail.address = divs[i + 1].get_text(strip=True)
                elif 'תאריך הגשה' in text_content and i + 1 < len(divs):
                    detail.submission_date = divs[i + 1].get_text(strip=True)

    def _extract_general_info(self, soup: BeautifulSoup, detail: RequestDetail):
        """Extract general info fields from info-main table."""
        info_main = soup.select_one('#info-main')
        if info_main:
            for row in info_main.select('tr'):
                cells = row.select('td')
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).rstrip(':')
                    value = cells[1].get_text(strip=True)
                    for hebrew, field_name in self.FIELD_MAP.items():
                        if hebrew in label:
                            setattr(detail, field_name, value)
                            break

    def _extract_stakeholders(self, soup: BeautifulSoup) -> list:
        """Extract stakeholders from table."""
        stakeholders = []
        rows = self.extract_table_rows(soup, '#table-baaley-inyan')
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 2:
                stakeholder = {
                    'role': self.get_cell_text(cells, 0),
                    'name': self.get_cell_text(cells, 1)
                }
                if stakeholder['name']:
                    stakeholders.append(stakeholder)
        return stakeholders

    def _extract_events(self, soup: BeautifulSoup) -> list:
        """Extract events/timeline from table."""
        events = []
        rows = self.extract_table_rows(soup, '#table-events')
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 4:
                event = {
                    'status': self.get_cell_text(cells, 0),
                    'event_type': self.get_cell_text(cells, 1),
                    'start_date': self.get_cell_text(cells, 2),
                    'end_date': self.get_cell_text(cells, 3)
                }
                if event['event_type']:
                    events.append(event)
        return events

    def _extract_requirements(self, soup: BeautifulSoup) -> list:
        """Extract requirements from table (note: typo in original HTML id)."""
        requirements = []
        requirements_div = soup.select_one('#requirments')  # Note: typo in original HTML
        if requirements_div:
            for row in requirements_div.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 2:
                    req = {
                        'requirement': self.get_cell_text(cells, 0),
                        'status': self.get_cell_text(cells, 1)
                    }
                    if req['requirement'] and req['requirement'] != '-':
                        requirements.append(req)
        return requirements

    def _extract_meetings(self, soup: BeautifulSoup) -> list:
        """Extract committee meetings from vaada section."""
        meetings = []
        vaada_div = soup.select_one('#vaada')
        if not vaada_div:
            return meetings

        # Try panel/accordion structure first
        for panel in vaada_div.select('.panel, .meeting-panel, [id^="meeting"]'):
            meeting = self._extract_meeting_from_panel(panel)
            if meeting:
                meetings.append(meeting)

        # Fall back to table structure if no panels found
        if not meetings:
            for table in vaada_div.select('table'):
                meeting_info = {}
                for row in table.select('tr'):
                    cells = row.select('td, th')
                    if len(cells) >= 2:
                        header = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        if 'מהות' in header:
                            meeting_info['description'] = value
                        elif 'החלטות' in header:
                            meeting_info['decisions'] = value
                if meeting_info:
                    meetings.append(meeting_info)

        return meetings

    def _extract_meeting_from_panel(self, panel) -> Optional[dict]:
        """Extract meeting info from a panel/accordion element."""
        meeting = {}

        # Try to get meeting header info
        header = panel.select_one('.panel-heading, .meeting-header, h4, h5')
        if header:
            meeting['header'] = header.get_text(strip=True)

        # Try structured extraction
        for row in panel.select('tr'):
            cells = row.select('td, th')
            if len(cells) >= 1:
                cell_text = cells[0].get_text(strip=True)
                if 'מהות' in cell_text and len(cells) > 1:
                    meeting['description'] = cells[1].get_text(strip=True)
                elif 'החלטות' in cell_text and len(cells) > 1:
                    meeting['decisions'] = cells[1].get_text(strip=True)

        # Try to extract meeting type and date from dedicated elements
        type_elem = panel.select_one('.vaada-type, .meeting-type')
        if type_elem:
            meeting['type'] = type_elem.get_text(strip=True)

        date_elem = panel.select_one('.vaada-date, .meeting-date')
        if date_elem:
            meeting['date'] = date_elem.get_text(strip=True)

        return meeting if meeting else None

    def _extract_documents(self, soup: BeautifulSoup) -> list:
        """Extract archive documents."""
        documents = []
        archive_div = soup.select_one('#archive')
        if archive_div:
            for row in archive_div.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 3:
                    doc = {
                        'name': self.get_cell_text(cells, 0),
                        'type': self.get_cell_text(cells, 1),
                        'date': self.get_cell_text(cells, 2)
                    }
                    if doc['name']:
                        documents.append(doc)
        return documents

    def _extract_gush_helka(self, soup: BeautifulSoup) -> list:
        """Extract parcel information."""
        parcels = []
        gush_table = soup.select_one('#gushim-helkot')
        if gush_table:
            for row in gush_table.select('tbody tr'):
                cells = row.select('td')
                if len(cells) >= 4:
                    gush_info = {
                        'gush': self.get_cell_text(cells, 0),
                        'helka': self.get_cell_text(cells, 1),
                        'migrash': self.get_cell_text(cells, 2),
                        'plan_number': self.get_cell_text(cells, 3)
                    }
                    if gush_info['gush'] or gush_info['helka']:
                        parcels.append(gush_info)
        return parcels


# Standalone function for backward compatibility with multiprocessing workers
def parse_request_detail(html: str, request_number: str, tik_number: str = "") -> dict:
    """
    Parse request detail HTML (standalone function for workers).

    This function is used by multiprocessing workers that need
    a module-level function for pickling.
    """
    parser = RequestDetailParser()
    return parser.parse_to_dict(html, request_number, tik_number)
