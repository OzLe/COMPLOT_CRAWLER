# Complot Building Permit Crawler

A unified crawler for Israeli municipality building permit systems powered by the Complot platform. Extracts building records, permit applications, and detailed property information from municipal engineering departments.

## Features

- **Multi-city support** - Pre-configured for 15+ Israeli municipalities
- **Smart street discovery** - Automatically finds all valid street codes
- **Parallel fetching** - Async HTTP requests with rate limiting (~150 records/sec)
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
python main.py netanya --skip-details

# Force re-fetch even if data exists
python main.py batyam --force

# Specify custom output directory
python main.py herzliya --output-dir ./my_data
```

### Using a URL

You can also pass a Complot URL directly:

```bash
python main.py "https://batyam.complot.co.il/iturbakashot/#search/..."
```

The crawler will auto-detect the city configuration from the URL.

## Available Cities

| City | Hebrew | Site ID | City Code |
|------|--------|---------|-----------|
| ofaqim | אופקים | 67 | 31 |
| batyam | בת ים | 81 | 6200 |
| netanya | נתניה | 62 | 7400 |
| ashdod | אשדוד | 65 | 70 |
| ashkelon | אשקלון | 66 | 7100 |
| beersheva | באר שבע | 68 | 9000 |
| herzliya | הרצליה | 71 | 6400 |
| raanana | רעננה | 78 | 8600 |
| rishon | ראשון לציון | 79 | 8300 |
| rehovot | רחובות | 80 | 8400 |
| petahtikva | פתח תקווה | 77 | 7900 |
| modiin | מודיעין | 75 | 1200 |
| holon | חולון | 72 | 6600 |
| ramatgan | רמת גן | 82 | 8600 |
| givatayim | גבעתיים | 70 | 6300 |

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
├── scripts/                # Utility & debug scripts
│   ├── analyze_building_detail.py
│   ├── analyze_city_api.py
│   └── ...
│
└── resources/              # Screenshots, samples
    ├── building_detail_screenshot.png
    └── ...
```

## Output Format

### streets.json
Discovered streets for the city:
```json
{
  "city": "בת ים",
  "total_streets": 196,
  "streets": [
    {"code": 100, "name": "אריק איינשטיין"},
    {"code": 101, "name": "קרן קימת לישראל"},
    ...
  ]
}
```

### building_records.json
Basic building file records:
```json
{
  "total_records": 6576,
  "records": [
    {
      "tik_number": "389000400",
      "address": "לוטוס 4 אופקים",
      "gush": "39668",
      "helka": "65",
      "street_code": 107,
      "street_name": "שדרות הרצל"
    },
    ...
  ]
}
```

### building_details.json
Detailed building information including permits:
```json
{
  "total_records": 6173,
  "records": [
    {
      "tik_number": "389000400",
      "address": "לוטוס 4 אופקים",
      "neighborhood": "רמת שקד",
      "gush_helka": [
        {"gush": "39668", "helka": "65", "migrash": "437", "plan_number": "128/03/23"}
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
      ]
    },
    ...
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

Typical performance on a standard connection:

| Operation | Speed |
|-----------|-------|
| Street discovery | ~100 codes/sec |
| Building records | ~50 records/sec |
| Building details | ~150 records/sec |

A full crawl of a medium-sized city (~6,000 buildings) takes approximately:
- Streets: 20-30 seconds
- Records: 2-5 minutes
- Details: 40-60 seconds

## API Reference

The crawler uses the Complot API at `handasi.complot.co.il`:

| Endpoint | Description |
|----------|-------------|
| `GetTikimByAddress` | Search building files by address |
| `GetBakashotByAddress` | Search permit requests by address |
| `GetTikFile` | Get detailed building file info |
| `GetRehovotByYeshuv` | Get streets list (not always available) |

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## Disclaimer

This tool is for informational purposes only. Building permit data is public information provided by Israeli municipalities. Please use responsibly and respect rate limits.
