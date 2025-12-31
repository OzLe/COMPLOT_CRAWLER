"""
Checkpoint management for crawler resumability.

Handles saving and loading of crawl progress to enable resuming interrupted crawls.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar

from src.utils.logging import get_logger

logger = get_logger()

T = TypeVar('T')


class CheckpointManager:
    """Manages checkpoint files for crawler resumability."""

    def __init__(self, output_dir: Path, city_name: str, city_name_en: str):
        """
        Initialize checkpoint manager.

        Args:
            output_dir: Directory for checkpoint files
            city_name: Hebrew city name (for metadata)
            city_name_en: English city name (for metadata)
        """
        self.output_dir = output_dir
        self.city_name = city_name
        self.city_name_en = city_name_en

        # Standard checkpoint file paths
        self.records_checkpoint = output_dir / "checkpoint.json"
        self.details_checkpoint = output_dir / "details_checkpoint.json"
        self.requests_checkpoint = output_dir / "requests_checkpoint.json"

    def save_records(self, records: List[Any]) -> None:
        """Save building records checkpoint."""
        output = {
            "city": self.city_name,
            "checkpoint_at": datetime.now().isoformat(),
            "total_records": len(records),
            "records": [asdict(r) if hasattr(r, '__dataclass_fields__') else r for r in records]
        }
        self._write_json(self.records_checkpoint, output)

    def save_details(self, details: List[Any]) -> None:
        """Save building details checkpoint."""
        checkpoint = {
            "city": self.city_name,
            "checkpoint_at": datetime.now().isoformat(),
            "total": len(details),
            "details": [asdict(d) if hasattr(d, '__dataclass_fields__') else d for d in details]
        }
        self._write_json(self.details_checkpoint, checkpoint)

    def save_requests(self, requests: List[Any], file_path: Optional[Path] = None) -> None:
        """Save request details checkpoint."""
        path = file_path or self.requests_checkpoint
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
        self._write_json(path, output)

    def load_details_checkpoint(self) -> Dict[str, Any]:
        """
        Load details checkpoint if it exists.

        Returns:
            Dictionary with 'details' key containing list of detail dicts,
            or empty dict if no checkpoint exists
        """
        if not self.details_checkpoint.exists():
            return {}

        try:
            data = self._read_json(self.details_checkpoint)
            if 'details' in data:
                logger.info(f"Loaded {len(data['details'])} records from checkpoint")
                return data
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")

        return {}

    def load_requests_checkpoint(self, file_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Load requests checkpoint if it exists.

        Returns:
            Dictionary with 'records' key containing list of request dicts,
            or empty dict if no checkpoint exists
        """
        path = file_path or self.requests_checkpoint
        if not path.exists():
            return {}

        try:
            data = self._read_json(path)
            if 'records' in data:
                logger.info(f"Loaded {len(data['records'])} request details from cache")
                return data
        except Exception as e:
            logger.warning(f"Failed to load request cache: {e}")

        return {}

    def _write_json(self, path: Path, data: Dict) -> None:
        """Write data to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _read_json(self, path: Path) -> Dict:
        """Read data from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
