# Alternative Data Sources for Building & Permit Details

**Date:** December 31, 2025
**Status:** Research Complete
**Purpose:** Identify alternative sources to retrieve building and request details blocked by Complot API

---

## Executive Summary

The Complot `GetTikFile` and `GetBakashaFile` APIs are blocked server-side. This research identified **multiple viable alternative data sources** that can enrich building records with the missing details.

### Key Findings

| Source | Data Available | Access Method | Viability |
|--------|----------------|---------------|-----------|
| **Tel Aviv GIS** | Building permits, dates, units, stages | ArcGIS REST API | ✅ High |
| **GovMap API** | Parcel/address lookup, cadastral data | JavaScript API | ✅ High |
| **iplan ArcGIS** | Planning zones, approved plans | ArcGIS REST API | ✅ Medium |
| **Meirim Project** | Planning alerts, permit tracking | Scraping (Puppeteer) | ⚠️ Medium |
| **CBS Statistics** | Aggregate building starts/completions | PDF/Excel downloads | ⚠️ Low |
| **Tabu Registry** | Ownership, legal status | Manual/paid service | ❌ Low |

---

## 1. Tel Aviv Municipal GIS (Highest Priority)

### Endpoint
```
https://gisn.tel-aviv.gov.il/arcgis/rest/services/IView2/MapServer/772
```

### Available Fields (Building Permits Layer)

| Field | Type | Description |
|-------|------|-------------|
| `request_num` | Integer | Request number (מספר בקשה) |
| `permission_date` | Date | Permission date (תאריך היתר) |
| `permission_num` | Integer | Permission number (מספר היתר) |
| `expiry_date` | Date | Permission expiry (תאריך תוקף היתר) |
| `open_request` | Date | Request opening date |
| `building_num` | Integer | Building code (קוד בניין) |
| `yechidot_diyur` | Integer | Housing units (יחידות דיור) |
| `building_stage` | String | Latest licensing activity |
| `addresses` | String | Addresses (כתובות) |

**Additional 36 fields** for TAMA-38 data, construction tracking, and completion dates.

### Query Capabilities
- Max record count: 2000
- Formats: JSON, geoJSON, PBF
- Spatial reference: EPSG:2039 (Israel TM)
- Supports: pagination, statistics, ordering, distinct values

### Example Query
```
https://gisn.tel-aviv.gov.il/arcgis/rest/services/IView2/MapServer/772/query
  ?where=1=1
  &outFields=request_num,permission_date,addresses,yechidot_diyur
  &f=json
```

### Other Relevant Layers

| Layer ID | Name | Description |
|----------|------|-------------|
| 499 | אתרי בניה | Construction sites |
| 513 | מבנים | Buildings |
| 528 | תוכניות בניין עיר | City building plans |
| 591 | מבנים מסוכנים | Dangerous buildings |
| 622 | אזורי רישוי בניה | Licensing zones |

---

## 2. GovMap API (Parcel/Address Enrichment)

### Documentation
- API Examples: https://www.govmap.gov.il/sites/api_examples.html
- JavaScript API: https://www.govmap.gov.il/govmap/api/govmap.api.js

### Key Functions

#### Address to Parcel Lookup
```javascript
govmap.searchAndLocate({
    type: govmap.locateType.addressToLotParcel,
    address: 'הרצל 1, תל אביב'
}).then(response => console.log(response));
```

#### Parcel to Address Lookup
```javascript
govmap.searchAndLocate({
    type: govmap.locateType.lotParcelToAddress,
    lot: 40095,
    parcel: 13
}).then(response => console.log(response));
```

### Available Layers
- `PARCEL_ALL` - All parcels
- `SUB_GUSH_ALL` - Sub-lot divisions
- `retzefMigrashim` - Development parcels

### Access Requirements
- Requires token registration via govmap@mapi.gov.il
- JavaScript-based (requires browser or Node.js execution)

---

## 3. iplan.gov.il ArcGIS Services (Planning Data)

### Service Base URL
```
https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/
```

### Known Services
- `Xplan/MapServer` - Approved plans (תוכניות מאושרות)
- `TAMA_1/MapServer` - National outline plans

### QGIS Integration
```
https://ags.iplan.gov.il/arcgisiplan/rest/services/PlanningPublic/Xplan/MapServer
```

### Service Discovery
Full service catalog: `https://ags.iplan.gov.il/services/?f=PlanningPublic&s=null`

### Note
Some endpoints return application errors. May need to use specific plan queries.

---

## 4. Meirim Open Source Project

### GitHub Repository
https://github.com/meirim-org/meirim

### Data Sources
- **mavat.iplan.gov.il** - Primary planning data
- **apps.land.gov.il** - Land authority data
- **GovMap** - Mapping integration

### Technology Stack
- Node.js with Puppeteer (headless Chrome)
- MongoDB database
- Cron-based crawling

### Crawl Schedule (Production)
```bash
# Crawl for new plans every 40 minutes
*/40 * * * * /meirim/bin/iplan

# Check status changes every 20 minutes
*/20 * * * * /meirim/bin/plan_status_change

# Tree permits at 10:00 and 21:00
0 10,21 * * 1-5 /meirim/bin/trees
```

### Potential Usage
Could adapt the mavat scraping logic for our needs, or use their scraped data if they expose an API.

---

## 5. Municipal Open Data Portals

### Haifa Data Portal
- URL: https://haifa.datacity.org.il/
- Datasets: Land use (ייעודי קרקע), neighborhoods, sub-districts
- Formats: SHP, CSV, XLSX, GeoJSON, XML, KML

### Jerusalem GIS
- URL: https://www1.jerusalem.muni.il/jer_sys/gis/open.htm
- ArcGIS hosted applications available
- Requires exploration for specific layers

### data.gov.il Datasets
- **Active Building Sites**: https://data.gov.il/dataset/buildingsites
- **iplan Planning Search**: https://data.gov.il/dataset/iplan-itur-tochnit

---

## 6. Central Bureau of Statistics (CBS)

### Building Starts Data
- URL: https://www.cbs.gov.il/he/subjects/Pages/התחלות-בנייה-וגמר-בנייה.aspx
- Data: Aggregate statistics on building starts and completions
- Formats: PDF, Excel
- Frequency: Monthly/Annual

### Limitation
Provides aggregate statistics, not individual building records. Useful for validation but not enrichment.

---

## 7. Land Registry (Tabu)

### Official Portal
- URL: https://mekarkein-online.justice.gov.il/

### Access Method
- Requires גוש/חלקה (block/parcel) numbers
- Fee per query
- Returns: ownership, liens, mortgages, easements

### API Status
**No public API available**. Access is manual via web interface or through paid third-party services (e.g., Dun & Bradstreet).

---

## Implementation Recommendations

### Phase 1: Tel Aviv GIS Integration (Immediate)

**Priority: HIGH**
**Effort: Low**
**Value: High**

```python
# Example implementation
async def fetch_tlv_permits(session, bbox=None, where="1=1"):
    url = "https://gisn.tel-aviv.gov.il/arcgis/rest/services/IView2/MapServer/772/query"
    params = {
        "where": where,
        "outFields": "*",
        "f": "json",
        "resultRecordCount": 2000
    }
    async with session.get(url, params=params) as resp:
        return await resp.json()
```

### Phase 2: GovMap Parcel Enrichment (Near-term)

**Priority: MEDIUM**
**Effort: Medium**
**Value: High**

Use GovMap API to:
1. Convert Complot addresses to גוש/חלקה
2. Fetch parcel boundaries and metadata
3. Cross-reference with other municipal data

### Phase 3: iplan Planning Data (Future)

**Priority: MEDIUM**
**Effort: High**
**Value: Medium**

Scrape mavat.iplan.gov.il for:
- Approved building plans
- Planning status
- Committee decisions

Consider adapting Meirim's Puppeteer-based approach.

### Phase 4: Multi-City GIS Aggregation (Future)

**Priority: LOW**
**Effort: High**
**Value: High**

Build adapters for each municipal GIS:
- Tel Aviv: ✅ Ready
- Haifa: Available via datacity.org.il
- Jerusalem: Available via ArcGIS
- Others: Need individual investigation

---

## Data Enrichment Flow

```
┌─────────────────────────────┐
│ Complot Crawler             │
│ (tik#, address, gush/helka) │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ GovMap API                  │
│ → Parcel boundaries         │
│ → Cadastral reference       │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Municipal GIS (per city)    │
│ → Permit dates              │
│ → Housing units             │
│ → Building stage            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ iplan/Mavat (optional)      │
│ → Planning status           │
│ → Approved plans            │
│ → Committee decisions       │
└─────────────────────────────┘
```

---

## Next Steps

1. **Create Tel Aviv GIS fetcher** - Implement ArcGIS REST client for Layer 772
2. **Investigate other city GIS endpoints** - Map out available layers per city
3. **Evaluate GovMap API access** - Request API token, test parcel lookups
4. **Consider Meirim integration** - Explore if they have API access or data sharing

---

## Sources

### Official Government Resources
- [GovMap](https://www.govmap.gov.il/) - Israel national mapping portal
- [GovMap API Examples](https://www.govmap.gov.il/sites/api_examples.html)
- [iplan.gov.il](https://mavat.iplan.gov.il/) - Planning administration
- [data.gov.il](https://data.gov.il/) - Open government data
- [CBS Building Data](https://www.cbs.gov.il/he/subjects/Pages/התחלות-בנייה-וגמר-בנייה.aspx)

### Municipal Portals
- [Tel Aviv Open Data](https://opendata.tel-aviv.gov.il/)
- [Tel Aviv GIS](https://gisn.tel-aviv.gov.il/arcgis/rest/services/IView2/MapServer)
- [Haifa Data Portal](https://haifa.datacity.org.il/)
- [Jerusalem GIS](https://www.jerusalem.muni.il/he/residents/planningandbuilding/gis-jerusalem/)

### Open Source Projects
- [Meirim](https://github.com/meirim-org/meirim) - Urban planning transparency
- [OpenTaba Server](https://github.com/niryariv/opentaba-server) - Planning data aggregator
- [Hasadna](https://www.hasadna.org.il/en/projects/) - Public Knowledge Workshop

---

*Research conducted December 31, 2025*
