# Complot Crawler Refactoring Plan

## Current State Analysis

### Problems Identified

1. **Monolithic `complot_crawler.py` (2,400 lines)**
   - Contains all logic: data models, parsers, fetchers, workers, storage, CLI
   - God class `ComplotCrawler` handles too many responsibilities
   - Hard to test, maintain, and extend

2. **Code Duplication**
   - HTML parsing logic duplicated between standalone worker functions and class methods
   - Similar fetch patterns repeated for streets, records, buildings, requests
   - Retry logic duplicated across all fetch operations

3. **Mixed Concerns**
   - Multiprocessing workers mixed with async code
   - Storage/checkpointing scattered throughout crawler class
   - CLI argument parsing in same file as business logic

4. **Configuration Coupling**
   - Constants (MAX_CONCURRENT, RETRY_DELAY) hardcoded at module level
   - No easy way to configure per-environment or per-city

---

## Proposed Modular Architecture

```
src/
├── __init__.py
├── config/
│   ├── __init__.py
│   ├── cities.py              # City configurations (from existing city_config.py)
│   └── settings.py            # API settings, constants, timeouts
│
├── models/
│   ├── __init__.py
│   ├── building.py            # BuildingRecord, BuildingDetail dataclasses
│   └── request.py             # RequestDetail dataclass
│
├── parsers/
│   ├── __init__.py
│   ├── base.py                # Base parser utilities (BeautifulSoup helpers)
│   ├── building_parser.py     # Parse GetTikFile HTML responses
│   ├── request_parser.py      # Parse GetBakashaFile HTML responses
│   └── search_parser.py       # Parse search result tables
│
├── fetchers/
│   ├── __init__.py
│   ├── base.py                # Base async fetcher with retry, semaphore, error handling
│   ├── street_fetcher.py      # Street discovery logic
│   ├── record_fetcher.py      # Building records by address
│   ├── building_fetcher.py    # Building detail fetcher
│   └── request_fetcher.py     # Request detail fetcher
│
├── workers/
│   ├── __init__.py
│   └── pool.py                # Multiprocessing worker functions
│
├── storage/
│   ├── __init__.py
│   ├── checkpoint.py          # Checkpoint save/load logic
│   └── exporter.py            # CSV and JSON export utilities
│
├── utils/
│   ├── __init__.py
│   ├── logging.py             # Logging setup and configuration
│   └── url_builder.py         # API URL construction
│
├── crawler.py                 # Main ComplotCrawler orchestrator (~200 lines)
└── cli.py                     # CLI argument parsing and entry point

main.py                        # Simple entry point
```

---

## Module Specifications

### 1. `src/config/settings.py` (~50 lines)
```python
@dataclass
class CrawlerSettings:
    api_base: str = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"
    max_concurrent: int = 20
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 2
    save_interval: int = 100
```

### 2. `src/config/cities.py` (~200 lines)
- Move existing `city_config.py` content here
- Keep `CityConfig` dataclass and `CITIES` dictionary

### 3. `src/models/building.py` (~60 lines)
```python
@dataclass
class BuildingRecord:
    tik_number: str
    address: str = ""
    gush: str = ""
    helka: str = ""
    ...

@dataclass
class BuildingDetail:
    tik_number: str
    address: str = ""
    neighborhood: str = ""
    ...
```

### 4. `src/models/request.py` (~50 lines)
```python
@dataclass
class RequestDetail:
    request_number: str
    tik_number: str = ""
    address: str = ""
    ...
```

### 5. `src/parsers/base.py` (~80 lines)
```python
class BaseParser:
    @staticmethod
    def get_text_safe(element, default="") -> str: ...

    @staticmethod
    def extract_table_rows(soup, table_id) -> list: ...

    @staticmethod
    def extract_header_field(soup, field_name) -> str: ...
```

### 6. `src/parsers/building_parser.py` (~150 lines)
```python
class BuildingDetailParser(BaseParser):
    def parse(self, html: str, tik_number: str) -> BuildingDetail: ...
    def _extract_address(self, soup) -> str: ...
    def _extract_gush_helka(self, soup) -> list: ...
    def _extract_requests(self, soup) -> list: ...
    def _extract_plans(self, soup) -> list: ...
```

### 7. `src/parsers/request_parser.py` (~200 lines)
```python
class RequestDetailParser(BaseParser):
    def parse(self, html: str, request_number: str, tik_number: str = "") -> RequestDetail: ...
    def _extract_general_info(self, soup) -> dict: ...
    def _extract_stakeholders(self, soup) -> list: ...
    def _extract_events(self, soup) -> list: ...
    def _extract_requirements(self, soup) -> list: ...
    def _extract_meetings(self, soup) -> list: ...
```

### 8. `src/parsers/search_parser.py` (~100 lines)
```python
class SearchResultParser(BaseParser):
    def parse_tikim_results(self, html: str, city_name: str) -> list[dict]: ...
    def parse_bakashot_results(self, html: str, city_name: str) -> list[dict]: ...
    def extract_street_name(self, html: str, city_name: str) -> Optional[str]: ...
```

### 9. `src/fetchers/base.py` (~100 lines)
```python
class BaseFetcher:
    def __init__(self, config: CityConfig, settings: CrawlerSettings): ...

    def build_url(self, program: str, **params) -> str: ...

    async def fetch_with_retry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        retry: int = 0
    ) -> Optional[str]: ...
```

### 10. `src/fetchers/street_fetcher.py` (~150 lines)
```python
class StreetFetcher(BaseFetcher):
    async def discover_streets(self, session, semaphore) -> list[dict]: ...
    async def test_street(self, session, street_code) -> Optional[dict]: ...
```

### 11. `src/fetchers/record_fetcher.py` (~150 lines)
```python
class RecordFetcher(BaseFetcher):
    async def fetch_records_for_street(self, session, street) -> list[BuildingRecord]: ...
    async def fetch_all_records(self, session, streets) -> list[BuildingRecord]: ...
```

### 12. `src/fetchers/building_fetcher.py` (~100 lines)
```python
class BuildingDetailFetcher(BaseFetcher):
    def __init__(self, config, settings, parser: BuildingDetailParser): ...
    async def fetch_detail(self, session, tik_number) -> BuildingDetail: ...
    async def fetch_all_details(self, session, tik_numbers) -> list[BuildingDetail]: ...
```

### 13. `src/fetchers/request_fetcher.py` (~100 lines)
```python
class RequestDetailFetcher(BaseFetcher):
    def __init__(self, config, settings, parser: RequestDetailParser): ...
    async def fetch_request(self, session, request_number, tik_number) -> RequestDetail: ...
    async def fetch_all_requests(self, session, request_items) -> list[RequestDetail]: ...
```

### 14. `src/workers/pool.py` (~200 lines)
```python
# Module-level functions for multiprocessing (must be picklable)
def worker_discover_streets(args: tuple) -> list[dict]: ...
def worker_fetch_records(args: tuple) -> list[dict]: ...
def worker_fetch_details(args: tuple) -> list[dict]: ...
def worker_fetch_requests(args: tuple) -> list[dict]: ...

class WorkerPool:
    def __init__(self, num_workers: int): ...
    def run_street_discovery(self, config_dict, ranges) -> list[dict]: ...
    def run_record_fetch(self, config_dict, street_chunks) -> list[dict]: ...
    def run_detail_fetch(self, config_dict, tik_chunks) -> list[dict]: ...
```

### 15. `src/storage/checkpoint.py` (~80 lines)
```python
class CheckpointManager:
    def __init__(self, output_dir: Path): ...
    def load_checkpoint(self, checkpoint_type: str) -> dict: ...
    def save_checkpoint(self, data: dict, checkpoint_type: str): ...
    def get_remaining(self, all_items: list, completed: dict) -> list: ...
```

### 16. `src/storage/exporter.py` (~150 lines)
```python
class DataExporter:
    def __init__(self, output_dir: Path): ...
    def export_streets(self, streets: list[dict], metadata: dict): ...
    def export_records(self, records: list[BuildingRecord], metadata: dict): ...
    def export_details(self, details: list[BuildingDetail], metadata: dict): ...
    def export_requests(self, requests: list[RequestDetail], metadata: dict): ...
    def export_csv(self, details, request_details): ...
```

### 17. `src/utils/logging.py` (~40 lines)
```python
def setup_logging(output_dir: Path, verbose: bool = False) -> logging.Logger: ...
```

### 18. `src/utils/url_builder.py` (~30 lines)
```python
def build_api_url(base: str, program: str, **params) -> str: ...
```

### 19. `src/crawler.py` (~200 lines)
```python
class ComplotCrawler:
    """Orchestrator that coordinates fetchers, workers, and storage"""

    def __init__(self, config: CityConfig, output_dir: str, workers: int = 1): ...

    async def discover_streets(self, force: bool = False) -> tuple[list, list]: ...
    async def fetch_building_records(self, streets, force: bool = False) -> list: ...
    async def fetch_building_details(self, records, resume: bool = True) -> list: ...
    async def fetch_request_details(self, details, force: bool = False) -> list: ...
    async def retry_failed_details(self) -> list: ...
    async def run_full_crawl(self, **options): ...
```

### 20. `src/cli.py` (~80 lines)
```python
def create_parser() -> argparse.ArgumentParser: ...
def main(): ...
```

---

## Implementation Order

### Phase 1: Extract Models (Low Risk)
1. Create `src/models/building.py` - move BuildingRecord, BuildingDetail
2. Create `src/models/request.py` - move RequestDetail
3. Create `src/config/settings.py` - extract constants
4. Update imports in existing code

### Phase 2: Extract Parsers (Medium Risk)
1. Create `src/parsers/base.py` - common utilities
2. Create `src/parsers/building_parser.py` - extract `_parse_building_detail_standalone`
3. Create `src/parsers/request_parser.py` - extract `_parse_request_detail_standalone`
4. Create `src/parsers/search_parser.py` - extract table parsing logic
5. Update existing code to use new parsers

### Phase 3: Extract Utilities (Low Risk)
1. Create `src/utils/logging.py` - move `setup_logging`
2. Create `src/utils/url_builder.py` - move URL building logic
3. Create `src/storage/checkpoint.py` - extract checkpoint logic
4. Create `src/storage/exporter.py` - extract export_csv and JSON export

### Phase 4: Extract Fetchers (High Risk - Core Logic)
1. Create `src/fetchers/base.py` - common fetch logic with retry
2. Create `src/fetchers/street_fetcher.py` - street discovery
3. Create `src/fetchers/record_fetcher.py` - building records
4. Create `src/fetchers/building_fetcher.py` - building details
5. Create `src/fetchers/request_fetcher.py` - request details

### Phase 5: Refactor Workers (Medium Risk)
1. Create `src/workers/pool.py` - consolidate worker functions
2. Update workers to use new fetchers and parsers

### Phase 6: Refactor Main Crawler (High Risk)
1. Simplify `src/crawler.py` to orchestrator role only
2. Create `src/cli.py` for argument parsing
3. Update `main.py` to use new structure

---

## Benefits After Refactoring

1. **Testability**: Each module can be unit tested independently
2. **Maintainability**: Changes isolated to relevant modules (~100-200 lines each)
3. **Reusability**: Parsers and fetchers can be reused in other tools
4. **Extensibility**: Easy to add new city types or data sources
5. **Clarity**: Clear separation of concerns

---

## File Size Summary (Estimated)

| Module | Lines | Responsibility |
|--------|-------|----------------|
| config/cities.py | ~200 | City configurations |
| config/settings.py | ~50 | Crawler settings |
| models/building.py | ~60 | Building data models |
| models/request.py | ~50 | Request data model |
| parsers/base.py | ~80 | Parser utilities |
| parsers/building_parser.py | ~150 | Building HTML parser |
| parsers/request_parser.py | ~200 | Request HTML parser |
| parsers/search_parser.py | ~100 | Search results parser |
| fetchers/base.py | ~100 | Base fetcher with retry |
| fetchers/street_fetcher.py | ~150 | Street discovery |
| fetchers/record_fetcher.py | ~150 | Record fetching |
| fetchers/building_fetcher.py | ~100 | Building detail fetching |
| fetchers/request_fetcher.py | ~100 | Request detail fetching |
| workers/pool.py | ~200 | Multiprocessing workers |
| storage/checkpoint.py | ~80 | Checkpoint management |
| storage/exporter.py | ~150 | Data export |
| utils/logging.py | ~40 | Logging setup |
| utils/url_builder.py | ~30 | URL construction |
| crawler.py | ~200 | Orchestrator |
| cli.py | ~80 | CLI interface |
| **Total** | **~2,270** | (vs 2,400 current, but distributed) |

All files stay under 200 lines, with clear single responsibilities.
