"""
Data export utilities for Complot Crawler.

Handles exporting crawled data to CSV and JSON formats.
"""

import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logging import get_logger

logger = get_logger()


class DataExporter:
    """Exports crawled data to various formats."""

    def __init__(self, output_dir: Path, city_name: str, city_name_en: str):
        """
        Initialize data exporter.

        Args:
            output_dir: Directory for output files
            city_name: Hebrew city name (for metadata)
            city_name_en: English city name (for metadata)
        """
        self.output_dir = output_dir
        self.city_name = city_name
        self.city_name_en = city_name_en

    def export_streets(self, streets: List[Dict], new_streets: List[Dict] = None,
                       previous_total: int = 0) -> Path:
        """Export discovered streets to JSON."""
        sorted_streets = sorted(streets, key=lambda x: x["code"])
        output = {
            "city": self.city_name,
            "city_en": self.city_name_en,
            "discovered_at": datetime.now().isoformat(),
            "total_streets": len(streets),
            "previous_total": previous_total,
            "new_streets_count": len(new_streets) if new_streets else 0,
            "new_streets": sorted(new_streets, key=lambda x: x["code"]) if new_streets else [],
            "streets": sorted_streets
        }

        streets_file = self.output_dir / "streets.json"
        self._write_json(streets_file, output)
        return streets_file

    def export_records(self, records: List[Any]) -> Path:
        """Export building records to JSON."""
        output = {
            "city": self.city_name,
            "city_en": self.city_name_en,
            "crawled_at": datetime.now().isoformat(),
            "total_records": len(records),
            "records": [asdict(r) if hasattr(r, '__dataclass_fields__') else r for r in records]
        }

        records_file = self.output_dir / "building_records.json"
        self._write_json(records_file, output)
        return records_file

    def export_details(self, details: List[Any]) -> Path:
        """Export building details to JSON."""
        success_count = sum(1 for d in details if getattr(d, 'fetch_status', None) == 'success')
        error_count = sum(1 for d in details if getattr(d, 'fetch_status', None) == 'error')

        output = {
            "city": self.city_name,
            "city_en": self.city_name_en,
            "fetched_at": datetime.now().isoformat(),
            "total_records": len(details),
            "success_count": success_count,
            "error_count": error_count,
            "records": [asdict(d) if hasattr(d, '__dataclass_fields__') else d for d in details]
        }

        details_file = self.output_dir / "building_details.json"
        self._write_json(details_file, output)
        return details_file

    def export_requests(self, requests: List[Any]) -> Path:
        """Export request details to JSON."""
        success_count = sum(1 for r in requests if getattr(r, 'fetch_status', None) == 'success')
        error_count = sum(1 for r in requests if getattr(r, 'fetch_status', None) == 'error')

        output = {
            "city": self.city_name,
            "city_en": self.city_name_en,
            "fetched_at": datetime.now().isoformat(),
            "total_records": len(requests),
            "success_count": success_count,
            "error_count": error_count,
            "records": [asdict(r) if hasattr(r, '__dataclass_fields__') else r for r in requests]
        }

        requests_file = self.output_dir / "request_details.json"
        self._write_json(requests_file, output)
        return requests_file

    def export_csv(self, details: List[Any], request_details: Optional[List[Any]] = None) -> List[Path]:
        """
        Export results to CSV files.

        Args:
            details: List of BuildingDetail objects
            request_details: Optional list of RequestDetail objects

        Returns:
            List of paths to created CSV files
        """
        exported_files = []

        # Main details CSV
        buildings_csv = self._export_buildings_csv(details)
        exported_files.append(buildings_csv)

        # Basic permits CSV
        permits_csv = self._export_permits_csv(details)
        exported_files.append(permits_csv)

        # Detailed exports if request details available
        if request_details:
            exported_files.extend(self._export_request_csvs(request_details))

        logger.info(f"Exported CSV files: {', '.join(f.name for f in exported_files)}")
        return exported_files

    def _export_buildings_csv(self, details: List[Any]) -> Path:
        """Export buildings summary CSV."""
        csv_file = self.output_dir / "buildings.csv"
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['tik_number', 'address', 'neighborhood', 'num_requests', 'num_plans'])
            for d in details:
                writer.writerow([
                    d.tik_number, d.address, d.neighborhood,
                    len(d.requests), len(d.plans)
                ])
        return csv_file

    def _export_permits_csv(self, details: List[Any]) -> Path:
        """Export basic permits CSV from building details."""
        permits_file = self.output_dir / "permits.csv"
        with open(permits_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'tik_number', 'address', 'request_number', 'submission_date',
                'last_event', 'applicant_name', 'permit_number', 'permit_date'
            ])
            for d in details:
                for req in d.requests:
                    writer.writerow([
                        d.tik_number, d.address,
                        req['request_number'], req['submission_date'],
                        req['last_event'], req['applicant_name'],
                        req['permit_number'], req['permit_date']
                    ])
        return permits_file

    def _export_request_csvs(self, request_details: List[Any]) -> List[Path]:
        """Export detailed request CSVs."""
        exported = []

        # Detailed permits CSV
        detailed_file = self.output_dir / "permits_detailed.csv"
        with open(detailed_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'request_number', 'tik_number', 'address', 'submission_date',
                'request_type', 'primary_use', 'description',
                'permit_number', 'permit_date',
                'main_area_sqm', 'service_area_sqm', 'housing_units',
                'num_stakeholders', 'num_events', 'num_requirements',
                'num_meetings', 'num_documents'
            ])
            for r in request_details:
                if r.fetch_status == 'success':
                    writer.writerow([
                        r.request_number, r.tik_number, r.address, r.submission_date,
                        r.request_type, r.primary_use, r.description,
                        r.permit_number, r.permit_date,
                        r.main_area_sqm, r.service_area_sqm, r.housing_units,
                        len(r.stakeholders), len(r.events), len(r.requirements),
                        len(r.meetings), len(r.documents)
                    ])
        exported.append(detailed_file)

        # Stakeholders CSV
        stakeholders_file = self.output_dir / "stakeholders.csv"
        with open(stakeholders_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['request_number', 'tik_number', 'role', 'name'])
            for r in request_details:
                if r.fetch_status == 'success':
                    for s in r.stakeholders:
                        writer.writerow([
                            r.request_number, r.tik_number,
                            s.get('role', ''), s.get('name', '')
                        ])
        exported.append(stakeholders_file)

        # Events CSV
        events_file = self.output_dir / "permit_events.csv"
        with open(events_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'request_number', 'tik_number', 'status',
                'event_type', 'start_date', 'end_date'
            ])
            for r in request_details:
                if r.fetch_status == 'success':
                    for e in r.events:
                        writer.writerow([
                            r.request_number, r.tik_number,
                            e.get('status', ''), e.get('event_type', ''),
                            e.get('start_date', ''), e.get('end_date', '')
                        ])
        exported.append(events_file)

        # Requirements CSV
        requirements_file = self.output_dir / "requirements.csv"
        with open(requirements_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['request_number', 'tik_number', 'requirement', 'status'])
            for r in request_details:
                if r.fetch_status == 'success':
                    for req in r.requirements:
                        writer.writerow([
                            r.request_number, r.tik_number,
                            req.get('requirement', ''), req.get('status', '')
                        ])
        exported.append(requirements_file)

        return exported

    def _write_json(self, path: Path, data: Dict) -> None:
        """Write data to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
