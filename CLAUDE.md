# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Complot Crawler is a multi-city web scraper for Israeli municipality building permit systems. It extracts building records, permit applications, and detailed property information from municipal engineering departments that use the Complot platform (`handasi.complot.co.il`).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Single city crawl
python main.py <city>                    # Full crawl (all 5 phases)
python main.py <city> --workers 4        # Parallel with 4 workers
python main.py <city> --streets-only     # Phase 1 only
python main.py <city> --skip-details     # Skip Phase 3
python main.py <city> --skip-requests    # Skip Phase 4
python main.py <city> --force            # Ignore cache, re-crawl
python main.py <city> --retry-errors     # Retry failed records only

# Batch crawl all cities
python crawl_all.py --workers 4 --parallel 2
python crawl_all.py --cities modiin,haifa --workers 4
python crawl_all.py --exclude batyam --dry-run

# List cities
python main.py --list-cities
```

## Architecture

### Crawl Flow (5 Phases)

1. **Street Discovery** - Brute-force scan street codes (1-2000) to find valid streets
2. **Building Records** - Fetch basic records via `GetTikimByAddress` / `GetBakashotByAddress`
3. **Building Details** - Fetch detailed building info via `GetTikFile`
4. **Request Details** - Fetch permit lifecycle via `GetBakashaFile` (events, stakeholders, requirements, decisions)
5. **CSV Export** - Export all data to CSV files

### Key Components

```
src/
├── complot_crawler.py      # Main crawler class + CLI entry point
├── config/
│   ├── cities.py           # City configurations (site_id, city_code, api_type)
│   └── settings.py         # Crawler settings (concurrency, timeouts, retries)
├── models/
│   ├── building.py         # BuildingRecord, BuildingDetail dataclasses
│   └── request.py          # RequestDetail dataclass
├── fetchers/               # Async HTTP fetchers for each phase
│   ├── street_fetcher.py
│   ├── record_fetcher.py
│   ├── building_fetcher.py
│   └── request_fetcher.py
├── parsers/                # HTML parsers (BeautifulSoup)
│   ├── building_parser.py
│   ├── request_parser.py
│   └── search_parser.py
├── storage/
│   ├── checkpoint.py       # Resume interrupted crawls
│   └── exporter.py         # JSON/CSV export
└── utils/
    └── logging.py          # Logging setup
```

### Parallelization

- **Single process**: 20 concurrent async HTTP connections
- **Multi-process** (`--workers N`): Each worker runs its own async event loop
- Progress updates via Rich progress bars with small chunks (10-20 items) for responsiveness

### API Types

- **tikim** - Building files system; permit details publicly accessible
- **bakashot** - Requests system; permit details require Israeli ID authentication (`--id`)

## Adding New Cities

Edit `src/config/cities.py`:

```python
"newcity": CityConfig(
    name="עיר חדשה",           # Hebrew name
    name_en="newcity",          # English name (for folders)
    site_id=XX,                 # From DevTools: siteid param
    city_code=XXXX,             # From DevTools: c param
    base_url="https://newcity.complot.co.il/",
    street_range=(1, 2000),
    api_type="tikim",           # or "bakashot"
    details_blocked=False       # True if GetTikFile is blocked
)
```

**Config Options:**
- `api_type`: "tikim" (building files) or "bakashot" (permit requests)
- `details_blocked`: Set to `True` if the municipality blocks public access to building details (GetTikFile returns error for all records). Crawler auto-skips Phases 3-4.

## Data Output

Output is saved to `data/<city>/`:
- `streets.json` - Discovered streets with incremental metadata
- `building_records.json` - Basic building records
- `building_details.json` - Detailed building info with permits
- `request_details.json` - Full permit lifecycle data
- CSV files: `buildings.csv`, `permits.csv`, `permits_detailed.csv`, `stakeholders.csv`, `permit_events.csv`, `requirements.csv`
- `crawler.log` - Timestamped logs

## API Reference

All endpoints at `handasi.complot.co.il/magicscripts/mgrqispi.dll`:
- `GetTikimByAddress` - Search building files by address
- `GetBakashotByAddress` - Search permit requests by address
- `GetTikFile` - Get detailed building file
- `GetBakashaFile` - Get detailed request (events, stakeholders, requirements)

See `docs/COMPLOT_API.md` for full API documentation.

## Working Cities

ofaqim, batyam*, beersheva, rehovot, modiin, yavne, ramathasharon

**All cities have `details_blocked=True`** - The Complot API has blocked public access to GetTikFile for all municipalities. Only basic building records (address, gush, helka) are available. Phases 3-4 are automatically skipped.

*batyam uses bakashot API requiring `--id` for searches

**Non-functional:** ashkelon, haifa (API returns no data)

## Code Search with Knowledge Graph

This project is indexed in the Knowledge Graph. Use the following MCP tools for efficient code exploration:

### Searching for Definitions

```
mcp__gkg-server__search_codebase_definitions
  search_terms: ["ComplotCrawler", "BuildingDetail", "fetch_building_details"]
  project_absolute_path: "/Users/ozlevi/Development/crawltest"
```

### Reading Definition Bodies

```
mcp__gkg-server__read_definitions
  definitions: [{"names": ["ComplotCrawler", "run_full_crawl"], "file_path": "src/complot_crawler.py"}]
```

### Finding All References

```
mcp__gkg-server__get_references
  definition_name: "BuildingRecord"
  absolute_file_path: "/Users/ozlevi/Development/crawltest/src/models/building.py"
```

### Repository Map (Directory Overview)

```
mcp__gkg-server__repo_map
  project_absolute_path: "/Users/ozlevi/Development/crawltest"
  relative_paths: ["src/fetchers", "src/parsers"]
  depth: 2
```

### Go to Definition

```
mcp__gkg-server__get_definition
  absolute_file_path: "/Users/ozlevi/Development/crawltest/src/complot_crawler.py"
  line: "from src.fetchers.building_fetcher import async_fetch_details_batch"
  symbol_name: "async_fetch_details_batch"
```

### Re-index After Major Changes

```
mcp__gkg-server__index_project
  project_absolute_path: "/Users/ozlevi/Development/crawltest"
```

**Prefer Knowledge Graph tools over grep/glob** for:
- Finding function/class definitions across the codebase
- Understanding call hierarchies and dependencies
- Impact analysis before refactoring
