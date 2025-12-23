# Complot Building Permit Crawler

A unified crawler for Israeli municipality building permit systems powered by the Complot platform. Extracts building records, permit applications, and detailed property information from municipal engineering departments.

## Features

- **Multi-city support** - Pre-configured for 6 Israeli municipalities
- **Smart street discovery** - Automatically finds all valid street codes by brute-force testing
- **Parallel fetching** - Async HTTP requests with configurable concurrency (20 concurrent requests)
- **Resume capability** - Checkpoint system to resume interrupted crawls
- **Multiple output formats** - JSON and CSV exports
- **URL auto-detection** - Pass a Complot URL to auto-configure city settings

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

# Only discover streets
python main.py ofaqim --streets-only

# Skip detailed info fetch (faster, basic records only)
python main.py ashkelon --skip-details

# Force re-fetch even if data exists
python main.py batyam --force

# Specify custom output directory
python main.py beersheva --output-dir ./my_data
```

### Using a URL

You can also pass a Complot URL directly:

```bash
python main.py "https://batyam.complot.co.il/iturbakashot/#search/..."
```

The crawler will auto-detect the city configuration from the URL.

## Supported Cities

| City | Hebrew | Site ID | Complot URL |
|------|--------|---------|-------------|
| ofaqim | אופקים | 67 | ofaqim.complot.co.il |
| batyam | בת ים | 81 | batyam.complot.co.il |
| ashkelon | אשקלון | 66 | ashkelon.complot.co.il |
| beersheva | באר שבע | 68 | br7.complot.co.il |
| rehovot | רחובות | 80 | rechovot.complot.co.il |
| modiin | מודיעין | 75 | modiin.complot.co.il |

## Project Structure

```
crawltest/
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── README.md
│
├── src/                    # Main source code
│   ├── __init__.py
│   ├── city_config.py      # City configurations
│   ├── complot_crawler.py  # Main crawler logic
│   └── fetch_building_details.py
│
├── data/                   # Output data (by city)
│   ├── batyam/
│   │   ├── streets.json
│   │   ├── building_records.json
│   │   ├── building_details.json
│   │   ├── buildings.csv
│   │   └── permits.csv
│   └── ofaqim/
│       └── ...
│
└── scripts/                # Utility & debug scripts
    ├── analyze_building_detail.py
    ├── analyze_city_api.py
    └── ...
```

## Output Format

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
- `buildings.csv` - Summary of all buildings
- `permits.csv` - All permit requests with details

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

The crawler uses async HTTP with 20 concurrent connections. Actual speed depends on network conditions and server response times.

| Operation | Concurrency | Notes |
|-----------|-------------|-------|
| Street discovery | 20 | Tests codes in batches of 100 |
| Building records | 5 | Lower concurrency for full street scans |
| Building details | 20 | With retry logic (3 retries, exponential backoff) |

Checkpoints are saved every 100 records (details) or 10 streets (records) to allow resuming interrupted crawls.

## API Reference

The crawler uses the Complot API at `handasi.complot.co.il`:

| Endpoint | Description |
|----------|-------------|
| `GetTikimByAddress` | Search building files by address (tikim API) |
| `GetBakashotByAddress` | Search permit requests by address (bakashot API) |
| `GetTikFile` | Get detailed building file info |

**Note:** Streets are discovered by brute-force testing street codes (1-2000) rather than using a streets API.

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Disclaimer

This tool is for informational purposes only. Building permit data is public information provided by Israeli municipalities. Please use responsibly and respect rate limits.
