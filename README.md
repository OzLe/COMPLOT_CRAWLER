# Complot Building Permit Crawler

A unified crawler for Israeli municipality building permit systems powered by the Complot platform. Extracts building records, permit applications, and detailed property information from municipal engineering departments.

## Features

- **Multi-city support** - Pre-configured for 9 Israeli municipalities
- **Two API types** - Supports both "tikim" (building files) and "bakashot" (requests) systems
- **Full permit lifecycle** - Extracts detailed permit data including events, stakeholders, requirements, and decisions
- **Multi-process parallelization** - Use `--workers N` to run N parallel processes for faster crawling
- **Batch crawling** - `crawl_all.py` script to crawl all cities with parallel execution
- **ID authentication** - Optional Israeli ID authentication for bakashot systems
- **Smart street discovery** - Automatically finds all valid street codes by brute-force testing
- **Incremental updates** - Detects new streets and only fetches records for newly discovered areas
- **Async HTTP** - Concurrent requests with configurable concurrency (20 concurrent per process)
- **Resume capability** - Checkpoint system to resume interrupted crawls
- **Logging** - Timestamped console and file logging with verbose mode
- **Multiple output formats** - JSON and CSV exports (buildings, permits, stakeholders, events, requirements)
- **URL auto-detection** - Pass a Complot URL to auto-configure city settings

## Crawl Phases

The crawler operates in 5 phases:

1. **Street Discovery** - Brute-force scan of street codes (1-2000) to find valid streets
2. **Building Records** - Fetch basic building file records for each street (`GetTikimByAddress`)
3. **Building Details** - Fetch detailed building file info for each record (`GetTikFile`)
4. **Request Details** - Fetch full permit lifecycle for each request (`GetBakashaFile`)
5. **CSV Export** - Export all data to CSV files for analysis

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd crawltest

# Install dependencies
pip install -r requirements.txt
```

### Dependencies

- `aiohttp` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `playwright` (optional) - For scripts that analyze page behavior
- `httpx` (optional) - Alternative HTTP client for scripts

## Usage

### Basic Commands

```bash
# List all available cities
python main.py --list-cities

# Crawl a city (full crawl: streets -> records -> details)
python main.py batyam

# Use 4 worker processes for faster crawling
python main.py modiin --workers 4

# Only discover streets
python main.py ofaqim --streets-only

# Skip detailed info fetch (faster, basic records only)
python main.py ashkelon --skip-details

# Force re-fetch even if data exists
python main.py batyam --force

# Specify custom output directory
python main.py beersheva --output-dir ./my_data

# Enable verbose logging (debug level)
python main.py batyam -v
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `city` | City name or Complot URL to crawl |
| `--list-cities` | List all available cities and exit |
| `--workers N` | Number of worker processes for parallel crawling (default: 1) |
| `--streets-only` | Only discover streets, skip building records |
| `--skip-details` | Skip detailed info fetch (faster, basic records only) |
| `--force` | Force re-fetch even if cached data exists |
| `--output-dir DIR` | Output directory (default: `data/`) |
| `-v, --verbose` | Enable verbose logging (debug level) |
| `--id ID` | Israeli ID number for bakashot authentication |

### Authenticated Fetching (Bakashot Systems)

Some cities (like Bat Yam) use the "bakashot" (requests) system which requires Israeli ID authentication to fetch permit details. Use the `--id` option:

```bash
# Fetch permits with ID authentication
python main.py batyam --id 123456789

# With verbose logging to see authentication status
python main.py batyam --id 123456789 -v
```

**Note:** Without `--id`, bakashot cities will only return basic building data (addresses, gush/helka) without detailed permit information.

### Using a URL

You can also pass a Complot URL directly:

```bash
python main.py "https://batyam.complot.co.il/iturbakashot/#search/..."
```

The crawler will auto-detect the city configuration from the URL.

### Crawling All Cities

Use `crawl_all.py` to crawl multiple cities in one command:

```bash
# List available cities
python crawl_all.py --list

# Preview what would be crawled (dry run)
python crawl_all.py --dry-run

# Crawl all cities sequentially with 4 workers per city
python crawl_all.py --workers 4

# Crawl 2 cities in parallel, 4 workers each
python crawl_all.py --workers 4 --parallel 2

# Only crawl specific cities
python crawl_all.py --cities modiin,ofaqim --workers 4

# Exclude specific cities (e.g., batyam needs auth)
python crawl_all.py --exclude batyam --workers 4

# Fast mode - skip building details
python crawl_all.py --skip-details --workers 4

# Force re-crawl everything
python crawl_all.py --force --workers 4 --parallel 2
```

#### crawl_all.py Options

| Option | Description |
|--------|-------------|
| `--workers N` | Workers per city (default: 1) |
| `--parallel N` | Cities to crawl simultaneously (default: 1) |
| `--cities a,b,c` | Only crawl specific cities |
| `--exclude a,b` | Exclude specific cities |
| `--force` | Force re-crawl (ignore cache) |
| `--skip-details` | Skip Phase 3 (faster) |
| `--dry-run` | Preview without running |
| `--list` | List available cities |

Results are saved to `data/crawl_summary.json`.

## Supported Cities

| City | Hebrew | Site ID | Complot URL | API Type |
|------|--------|---------|-------------|----------|
| ofaqim | אופקים | 67 | ofaqim.complot.co.il | tikim |
| batyam | בת ים | 81 | batyam.complot.co.il | bakashot* |
| ashkelon | אשקלון | 66 | ashkelon.complot.co.il | tikim |
| beersheva | באר שבע | 68 | br7.complot.co.il | tikim |
| rehovot | רחובות | 80 | rechovot.complot.co.il | tikim |
| modiin | מודיעין-מכבים-רעות | 82 | modiin.complot.co.il | tikim |
| haifa | חיפה | 16 | haifa.complot.co.il | tikim |
| yavne | יבנה | 87 | yavne.complot.co.il | tikim |
| ramathasharon | רמת השרון | 118 | ramathasharon.complot.co.il | tikim |

*\*bakashot cities require `--id` for full permit details*

### API Types Explained

- **tikim** (תיקים) - Building files system. Permit details are publicly accessible via `GetTikFile` API.
- **bakashot** (בקשות) - Requests system. Permit details require Israeli ID authentication via `GetBakashaFile` API.

## Documentation

See [docs/COMPLOT_API.md](docs/COMPLOT_API.md) for comprehensive API documentation including:
- All available endpoints and parameters
- Response structure and field descriptions
- Data relationships between building files and permits
- Hebrew-English glossary

## Project Structure

```
crawltest/
├── main.py                 # Single-city entry point
├── crawl_all.py            # Multi-city batch crawler
├── requirements.txt        # Python dependencies
├── README.md
│
├── src/                    # Main source code
│   ├── __init__.py
│   ├── city_config.py      # City configurations and URL parsing
│   └── complot_crawler.py  # Main crawler logic (with multiprocessing)
│
├── docs/                   # Documentation
│   └── COMPLOT_API.md      # Full API documentation
│
├── data/                   # Output data (by city)
│   ├── crawl_summary.json  # Summary from crawl_all.py
│   ├── batyam/
│   │   ├── streets.json           # Discovered streets
│   │   ├── building_records.json  # Basic building records
│   │   ├── building_details.json  # Building file details (GetTikFile)
│   │   ├── request_details.json   # Detailed permit lifecycle (GetBakashaFile)
│   │   ├── buildings.csv          # Building summary
│   │   ├── permits.csv            # Basic permit list
│   │   ├── permits_detailed.csv   # Full permit info with areas
│   │   ├── stakeholders.csv       # Applicants, architects, engineers
│   │   ├── permit_events.csv      # Permit timeline events
│   │   ├── requirements.csv       # Permit requirements
│   │   └── crawler.log
│   └── ofaqim/
│       └── ...
│
└── scripts/                # Utility & debug scripts
    ├── analyze_building_detail.py
    ├── analyze_city_api.py
    ├── analyze_page.py
    ├── api_crawler.py
    ├── crawler.py
    ├── debug_crawl.py
    ├── debug_street.py
    ├── discover_streets.py
    └── full_city_crawler.py
```

## Output Files

### streets.json
Discovered streets for the city:
```json
{
  "city": "בת ים",
  "city_en": "batyam",
  "site_id": 81,
  "city_code": 6200,
  "discovered_at": "2025-12-23T16:47:28.018021",
  "total_streets": 196,
  "streets": [
    {"code": 100, "name": "אריק איינשטיין"},
    {"code": 101, "name": "קרן קימת לישראל"}
  ]
}
```

### building_records.json
Basic building file records:
```json
{
  "city": "אופקים",
  "city_en": "ofaqim",
  "crawled_at": "2025-12-23T14:47:00.000000",
  "total_records": 6576,
  "records": [
    {
      "tik_number": "389000400",
      "address": "לוטוס 4 אופקים",
      "gush": "39668",
      "helka": "65",
      "migrash": "",
      "street_code": 107,
      "street_name": "שדרות הרצל",
      "house_number": 4
    }
  ]
}
```

### building_details.json
Detailed building information including permits:
```json
{
  "city": "אופקים",
  "city_en": "ofaqim",
  "fetched_at": "2025-12-23T14:53:58.022953",
  "total_records": 6173,
  "success_count": 6173,
  "error_count": 0,
  "records": [
    {
      "tik_number": "389000400",
      "address": "לוטוס 4 אופקים",
      "neighborhood": "רמת שקד",
      "addresses": ["לוטוס 4 אופקים"],
      "gush_helka": [
        {"gush": "39668", "helka": "65", "migrash": "437", "plan_number": "128/03/23"}
      ],
      "plans": [
        {"plan_number": "128/03/23", "plan_name": "תכנית מפורטת", "status": "בתוקף", "status_date": ""}
      ],
      "requests": [
        {
          "request_number": "20160126",
          "submission_date": "14/06/2016",
          "last_event": "הוצאת היתר בניה",
          "applicant_name": "שישפורטיש אילנית",
          "permit_number": "20160126",
          "permit_date": "10/08/2016"
        }
      ],
      "stakeholders": [],
      "documents": [],
      "fetch_status": "success",
      "fetch_error": "",
      "fetched_at": "2025-12-23T14:53:18.244101"
    }
  ]
}
```

### CSV Files
- `buildings.csv` - Summary of all buildings (tik_number, address, neighborhood, num_requests, num_plans)
- `permits.csv` - All permit requests with details (tik_number, address, request_number, dates, applicant, permit info)

### crawler.log
Timestamped log file with all crawler activity:
```
2025-12-24 10:12:00 | INFO     | Logging initialized. Log file: data/batyam/crawler.log
2025-12-24 10:12:00 | INFO     | ############################################################
2025-12-24 10:12:00 | INFO     | COMPLOT CRAWLER - בת ים (batyam)
2025-12-24 10:12:00 | INFO     | ############################################################
2025-12-24 10:12:00 | INFO     | Site ID: 81
2025-12-24 10:12:00 | INFO     | City Code: 6200
2025-12-24 10:12:00 | INFO     | API Type: bakashot
```

## Adding New Cities

Edit `src/city_config.py` and add a new entry:

```python
"newcity": CityConfig(
    name="עיר חדשה",           # Hebrew name
    name_en="newcity",          # English name (for folders/files)
    site_id=XX,                 # Complot site ID
    city_code=XXXX,             # CBS city code
    base_url="https://newcity.complot.co.il/",
    street_range=(1, 2000),     # Range of street codes to scan
    api_type="tikim"            # "tikim" or "bakashot"
)
```

To find the site ID and city code:
1. Visit the city's Complot portal
2. Open browser DevTools (F12)
3. Look for API calls to `handasi.complot.co.il` containing `siteid` and `c` parameters

## Performance

The crawler uses async HTTP with 20 concurrent connections per process. Use `--workers N` to run multiple processes in parallel for faster crawling.

### Single Process (default)

| Operation | Concurrency | Notes |
|-----------|-------------|-------|
| Street discovery | 20 | Tests codes in batches of 100 |
| Building records | 5 | Lower concurrency for full street scans |
| Building details | 20 | With retry logic (3 retries, exponential backoff) |

### Multi-Process (`--workers N`)

Each worker runs its own async event loop with 20 concurrent connections:

| Workers | Effective Concurrency | Speedup |
|---------|----------------------|---------|
| 1 | 20 connections | Baseline |
| 2 | 40 connections | ~1.8x |
| 4 | 80 connections | ~3x |
| 8 | 160 connections | ~4-5x |

**Example:**
```bash
# Single process: ~100 seconds for 2000 streets
python main.py modiin --workers 1 --streets-only

# 4 workers: ~30 seconds for 2000 streets
python main.py modiin --workers 4 --streets-only
```

Checkpoints are saved every 100 records (details) or 10 streets (records) to allow resuming interrupted crawls.

## API Reference

The crawler uses the Complot API at `handasi.complot.co.il`:

| Endpoint | Description | Auth Required |
|----------|-------------|---------------|
| `GetTikimByAddress` | Search building files by address (tikim API) | No |
| `GetBakashotByAddress` | Search permit requests by address (bakashot API) | No |
| `GetTikFile` | Get detailed building file info | No |
| `GetBakashaFile` | Get detailed request info | Yes (Israeli ID) |

**Note:** Streets are discovered by brute-force testing street codes (1-2000) rather than using a streets API.

## Logging

The crawler automatically creates logs in the city's output directory:

- **Console**: INFO level by default, DEBUG with `-v` flag
- **File**: Always DEBUG level, saved to `data/<city>/crawler.log`

Log format:
```
YYYY-MM-DD HH:MM:SS | LEVEL    | Message
```

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Disclaimer

This tool is for informational purposes only. Building permit data is public information provided by Israeli municipalities. Please use responsibly and respect rate limits.
