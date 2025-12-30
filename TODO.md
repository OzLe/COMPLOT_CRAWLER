# Complot Crawler - TODO

## Last Updated: 2025-12-25

---

## Completed Tasks

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

---

## Pending Tasks

### Cities to Investigate Further
These cities have accessible Complot portals but returned 0 streets with current API:

| City | Hebrew | Site ID | Notes |
|------|--------|---------|-------|
| ksaba | כפר סבא | 13 | Portal accessible, API returns no data |
| hodhasharon | הוד השרון | 33 | Portal accessible, API returns no data |

Possible reasons:
- Different API structure (not standard tikim/bakashot)
- Different city_code format needed
- May require authentication

### Cities with Partial Access (from validation script)
These had accessible subdomains but site_id wasn't found automatically:
- givatayim, ramatgan, holon, petahtikva, netanya, herzliya, raanana, rishonlezion (different subdomain?)

### API Coverage Testing
- [ ] Test GetTikFile API for new cities (yavne returned "no data available" for details)
- [ ] Verify if some cities only support basic records without detailed permit info
- [ ] Consider adding a "details_available" flag to CityConfig

### Feature Ideas
- [ ] Add progress bars for long-running operations
- [ ] Add email/webhook notifications when crawl completes
- [ ] Create a web dashboard for viewing crawled data
- [ ] Add data validation/sanity checks after crawl
- [ ] Export to SQLite/PostgreSQL for easier querying

### Documentation
- [ ] Add troubleshooting section to README
- [ ] Document how to find site_id for new cities
- [ ] Add examples of common queries on crawled data

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
