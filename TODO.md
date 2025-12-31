# Complot Crawler - TODO

## Last Updated: 2025-12-31

---

## Completed Tasks

### City Investigation (Dec 30, 2025)
- [x] Investigated ksaba (Kfar Saba) and hodhasharon - confirmed non-functional with standard API
- [x] Tested partial access cities - most use different systems (ONECity, municipal portals)
- [x] Verified GetTikFile API works for all 3 new cities (Haifa, Yavne, Ramat HaSharon)
- [x] Confirmed all new cities support full building details (not just basic records)

### Multi-Worker Parallelization
- [x] Added `--workers N` CLI argument for parallel processing
- [x] Implemented multiprocessing.Pool for all three phases:
  - Street discovery
  - Building records fetching
  - Building details fetching
- [x] Tested with 4-8 workers showing ~3-4x speedup

### Batch Crawling Script
- [x] Created `crawl_all.py` for crawling multiple cities
- [x] Supports `--parallel N` for running cities simultaneously
- [x] Supports `--cities`, `--exclude`, `--dry-run`, `--list` options

### City Validation (Dec 2025)
- [x] Validated ~40 cities from user's list
- [x] Added 3 new working cities:
  - Haifa (site_id=16, 975 streets)
  - Yavne (site_id=87, 200 streets)
  - Ramat HaSharon (site_id=118, 307 streets)
- [x] Updated README.md with new cities

### Bug Fixes
- [x] Fixed Modiin site_id (was 75, now 82)
- [x] Fixed empty CSV exports issue (caused by stale cache)

### Progress Bars (Dec 31, 2025)
- [x] Added tqdm progress bars for all long-running operations:
  - Street discovery: shows codes tested, found count
  - Building records fetching: shows streets processed, records found
  - Building details fetching: shows buildings processed, success/error counts

### Incremental Street Detection (Dec 31, 2025)
- [x] When streets.json exists, automatically detects new streets
- [x] Compares fresh API scan against cached baseline
- [x] Only fetches building records for newly discovered streets
- [x] Updated streets.json schema with incremental metadata (previous_total, new_streets_count, new_streets)

### Retry Errors Feature (Dec 31, 2025)
- [x] Added `--retry-errors` CLI flag to re-fetch failed building details
- [x] Loads existing building_details.json and retries only error records
- [x] Updates file in-place with recovered records

### API Documentation (Dec 31, 2025)
- [x] Created comprehensive API documentation at `docs/COMPLOT_API.md`
- [x] Documented all endpoints: GetTikimByAddress, GetBakashotByAddress, GetTikFile, GetBakashaFile
- [x] Documented GetBakashaFile response structure (events, stakeholders, requirements, meetings)
- [x] Added Hebrew-English glossary

---

## Pending Tasks

### Non-Functional Cities (Investigated Dec 30, 2025)
These cities were investigated and confirmed non-functional with the standard Complot API:

| City | Hebrew | Site ID | Status |
|------|--------|---------|--------|
| ksaba | כפר סבא | 13 | Portal accessible, API returns no data for any city_code/street combo |
| hodhasharon | הוד השרון | 33 | Portal accessible, API returns no data |
| ashdod | אשדוד | N/A | Redirects to municipal portal (digital.ashdod.muni.il) |
| rishonlezion | ראשון לציון | N/A | Uses ONECity platform (WordPress), not Complot handasi |
| dimona | דימונה | N/A | Subdomain exists but no site_id, likely different system |
| eilat | אילת | N/A | Subdomain exists but no site_id |

Cities with no accessible subdomain:
- givatayim, holon, petahtikva, netanya, herzliya, raanana (connection refused)

### Feature Ideas
- [ ] Add email/webhook notifications when crawl completes
- [ ] Create a web dashboard for viewing crawled data
- [ ] Add data validation/sanity checks after crawl
- [ ] Export to SQLite/PostgreSQL for easier querying

### Documentation
- [x] Created comprehensive API documentation (docs/COMPLOT_API.md)
- [ ] Add troubleshooting section to README
- [ ] Add examples of common queries on crawled data

### Future Enhancements
- [ ] Add GetBakashaFile support for detailed permit data (events, stakeholders, requirements, meetings)
- [ ] Parse document archive links from GetBakashaFile responses

---

## Quick Reference

### Run Commands
```bash
# List all cities
python main.py --list-cities

# Crawl single city with 4 workers
python main.py haifa --workers 4

# Crawl all cities
python crawl_all.py --workers 4 --parallel 2

# Streets only (fast test)
python main.py yavne --streets-only --workers 4

# Force re-crawl
python main.py modiin --force --workers 4
```

### Key Files
- `src/city_config.py` - City configurations (site_id, city_code, etc.)
- `src/complot_crawler.py` - Main crawler logic
- `crawl_all.py` - Batch crawler script
- `scripts/validate_cities.py` - City validation script

### Data Output
- `data/<city>/streets.json` - Discovered streets
- `data/<city>/building_records.json` - Basic building records
- `data/<city>/building_details.json` - Detailed permit info
- `data/<city>/buildings.csv` - Building summary
- `data/<city>/permits.csv` - All permits
- `data/<city>/crawler.log` - Crawl logs

---

## Notes

### City Codes
- CBS (Central Bureau of Statistics) codes are used for city_code
- Some cities may use different internal codes (e.g., Haifa uses 4000 not the CBS code)
- The `c` parameter in API calls refers to city_code

### API Endpoints
- `GetTikimByAddress` - Search building files (tikim)
- `GetBakashotByAddress` - Search permit requests (bakashot)
- `GetTikFile` - Get detailed building file
- `GetBakashaFile` - Get detailed request (requires Israeli ID)

### Known Limitations
- Some cities (like Bat Yam) require Israeli ID for detailed permit info
- Street codes are discovered by brute-force (1-2000 range)
- Some cities may have limited public data access

### City Infrastructure Findings (Dec 2025)
Many Israeli municipalities have migrated away from the standard Complot handasi backend:
- **ONECity Platform**: rishonlezion uses WordPress-based ONECity (dpo@onecity.co.il)
- **Municipal Portals**: ashdod redirects to digital.ashdod.muni.il
- **Legacy Complot (non-functional)**: ksaba, hodhasharon have portals but API returns no data
- **Working Cities**: ofaqim, batyam, ashkelon, beersheva, rehovot, modiin, haifa, yavne, ramathasharon
