# Complot Building Permit API Documentation

## Overview

The Complot system is used by Israeli municipalities to manage building permits and construction files.
The API is hosted at `https://handasi.complot.co.il/magicscripts/mgrqispi.dll` and serves multiple cities through a `siteid` parameter.

## Base URL

```
https://handasi.complot.co.il/magicscripts/mgrqispi.dll?appname=cixpa&prgname={PROGRAM}&{PARAMS}&arguments={ARG_LIST}
```

## Authentication

Most endpoints are publicly accessible. Document downloads may require session authentication.

---

## Endpoints

### 1. GetTikimByAddress

Search for building files (תיקי בניין) by address.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `siteid` | int | City site ID |
| `c` | int | City code (CBS code or internal) |
| `s` | int | Street code |
| `h` | int | House number |
| `l` | string | Limit results ("true") |

**Example Request:**
```
GET /mgrqispi.dll?appname=cixpa&prgname=GetTikimByAddress&siteid=118&c=2650&s=10&h=5&l=true&arguments=siteid,c,s,h,l
```

**Response:** HTML table with building file records containing:
- `tik_number` - Building file number
- `address` - Full address
- `gush` - Land block number
- `helka` - Land parcel number

---

### 2. GetBakashotByAddress

Search for permit requests (בקשות להיתר) by address.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `siteid` | int | City site ID |
| `grp` | int | Group (usually 0) |
| `t` | int | Type (usually 1) |
| `c` | int | City code |
| `s` | int | Street code |
| `h` | int | House number |
| `l` | string | Limit results ("true") |

**Example Request:**
```
GET /mgrqispi.dll?appname=cixpa&prgname=GetBakashotByAddress&siteid=81&grp=0&t=1&c=6200&s=10&h=5&l=true&arguments=siteId,grp,t,c,s,h,l
```

**Response:** HTML table with permit request records.

---

### 3. GetTikFile

Get detailed information about a building file (תיק בניין).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `siteid` | int | City site ID |
| `t` | string | Building file number (tik_number) |

**Example Request:**
```
GET /mgrqispi.dll?appname=cixpa&prgname=GetTikFile&siteid=118&t=3658&arguments=siteid,t
```

**Response Structure:**

```
#result-title-div-id    - Header with address
#info-main              - General information table
#addresses              - Associated addresses list
#table-gushim-helkot    - Land parcels (gush/helka)
#table-requests         - Permit requests summary
#table-taba             - Urban plans list
```

**Extracted Data:**

| Field | Source | Description |
|-------|--------|-------------|
| `address` | Header | Primary address |
| `neighborhood` | info-main | Neighborhood name |
| `addresses` | #addresses | All associated addresses |
| `gush_helka` | #table-gushim-helkot | Land parcel details |
| `requests` | #table-requests | List of permit requests |
| `plans` | #table-taba | Associated urban plans |

**Request Fields:**

| Field | Description |
|-------|-------------|
| `request_number` | Permit request number |
| `submission_date` | Date submitted |
| `last_event` | Most recent event/status |
| `applicant_name` | Applicant name |
| `permit_number` | Issued permit number |
| `permit_date` | Permit issue date |

---

### 4. GetBakashaFile

Get detailed information about a specific permit request (בקשה להיתר).

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `siteid` | int | City site ID |
| `b` | string | Request number (bakasha number) |

**Example Request:**
```
GET /mgrqispi.dll?appname=cixpa&prgname=GetBakashaFile&siteid=118&b=20170232&arguments=siteid,b
```

**Response Structure:**

```
#info-main          - General permit information
#mahut              - Request nature/description
#baaley-inyan       - Stakeholders table
#gushim-helkot      - Land parcels
#events             - Event timeline (full history)
#vaada              - Committee meetings
#requirments        - Permit requirements
#archive            - Documents archive
```

**General Info Fields (#info-main):**

| Field (Hebrew) | Field (English) | Description |
|----------------|-----------------|-------------|
| מספר תיק בניין | building_file_number | Associated building file |
| סוג הבקשה | request_type | Type of request |
| שימוש עיקרי | primary_use | Primary building use |
| תיאור הבקשה | description | Request description |
| מספר היתר | permit_number | Issued permit number |
| תאריך הפקת היתר | permit_date | Permit issue date |
| שטח עיקרי | main_area_sqm | Main area in sqm |
| שטח שירות | service_area_sqm | Service area in sqm |
| סך מספר יחידות דיור | housing_units | Number of housing units |

**Stakeholders (#baaley-inyan):**

| Role (Hebrew) | Role (English) |
|---------------|----------------|
| מבקש | applicant |
| עורך הבקשה | request_editor (architect) |
| אחראי שלד | structural_engineer |
| קבלן | contractor |

**Events (#events):**

| Column | Description |
|--------|-------------|
| Status | Current/Closed (נוכחי/סגור) |
| Event Type | Type of event |
| Start Date | Event start date |
| End Date | Event end date |

**Requirements (#requirments):**

| Column | Description |
|--------|-------------|
| Requirement | Description of requirement |
| Status | Completion status (הושלם = completed) |

**Documents (#archive):**

| Column | Description |
|--------|-------------|
| Document Name | Name/description |
| Document Type | Category (היתר, תשריט, etc.) |
| Date | Upload/creation date |

**Committee Meetings (#vaada):**

| Field | Description |
|-------|-------------|
| Meeting Type | Committee type (רשות רישוי, ועדת משנה) |
| Meeting Number | Meeting ID |
| Date/Time | Meeting date and time |
| Mahut | Request description discussed |
| Decisions | Full decision text |

---

### 5. GetRequestArchiveFile

Download a document from the permit archive.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `siteid` | int | City site ID |
| `RequestId` | string | Request number |
| `FileType` | int | File type code |
| `ArchiveNumber` | int | Archive index number |

**Example Request:**
```
GET /mgrqispi.dll?appname=cixpa&prgname=GetRequestArchiveFile&siteid=118&RequestId=20170232&FileType=0&ArchiveNumber=9&arguments=siteid,RequestId,FileType,ArchiveNumber
```

**Note:** This endpoint may require session authentication or cookies from the web portal.

---

## City Configuration

### Important: API Status (December 2025)

**All cities now have GetTikFile blocked.** The Complot API has restricted public access to building file details across all municipalities. Only basic building records from address searches are available.

### Working Cities (Records Only)

| City | Hebrew | Site ID | City Code | API Type | Status |
|------|--------|---------|-----------|----------|--------|
| ofaqim | אופקים | 67 | 31 | tikim | Search OK, Details Blocked |
| batyam | בת ים | 81 | 6200 | bakashot | Search OK, Details Blocked |
| beersheva | באר שבע | 105 | 9000 | tikim | Search OK, Details Blocked |
| rehovot | רחובות | 22 | 8400 | tikim | Search OK, Details Blocked |
| modiin | מודיעין | 82 | 1200 | tikim | Search OK, Details Blocked |
| yavne | יבנה | 87 | 2660 | tikim | Search OK, Details Blocked |
| ramathasharon | רמת השרון | 118 | 2650 | tikim | Search OK, Details Blocked |

**Available Data for All Cities:**
- Tik number, address, gush, helka from GetTikimByAddress
- No permit details, stakeholders, events, or documents (GetTikFile blocked)

The crawler automatically skips Phases 3-4 when `details_blocked=True`.

### Non-Functional Cities

These cities have Complot portals but the API returns no data:

| City | Site ID | Notes |
|------|---------|-------|
| ashkelon | 66 | Portal accessible, search API returns no data |
| haifa | 16 | Portal accessible, search API returns no data |
| ksaba (Kfar Saba) | 13 | Portal accessible, API returns no data |
| hodhasharon | 33 | Portal accessible, API returns no data |
| ashdod | N/A | Redirects to municipal portal |
| rishonlezion | N/A | Uses ONECity platform |

---

## Street Discovery

Streets are discovered by brute-force testing street codes (1-2000).
A street is valid if any house number returns building records.

**Test House Numbers:** `[1, 2, 3, 5, 10, 20, 50]`

---

## Data Relationships

```
City
 └── Streets (discovered via brute-force)
      └── Building Files (תיקי בניין) via GetTikimByAddress
           ├── Addresses
           ├── Land Parcels (Gush/Helka)
           ├── Urban Plans
           └── Permit Requests (בקשות)
                └── Request Details via GetBakashaFile
                     ├── General Info (areas, use, description)
                     ├── Stakeholders
                     ├── Event Timeline
                     ├── Committee Meetings + Decisions
                     ├── Requirements + Status
                     └── Document Archive
```

---

## Response Formats

All endpoints return HTML fragments (not JSON). Data must be parsed using BeautifulSoup or similar HTML parser.

### Common Patterns

**No Results:**
```html
<div class="hidden-error">ERR_NO_RESULTS</div>
```

**Data Not Available:**
```html
<p translatable-text>לא ניתן להציג את המידע המבוקש.</p>
```

**Success:** HTML tables with `<tbody>` containing data rows.

---

## Rate Limiting

No explicit rate limits observed, but recommended:
- Max 20 concurrent requests
- 2-second delay between retries
- 3 max retries per request

---

## Example: Full Data Extraction Flow

```python
# 1. Discover streets for a city
for street_code in range(1, 2000):
    response = get_tikim_by_address(siteid, city_code, street_code, house=1)
    if has_results(response):
        streets.append(extract_street_info(response))

# 2. Get building files for each street
for street in streets:
    for house in [1, 2, 3, 5, 10, 20, 50]:
        buildings = get_tikim_by_address(siteid, city_code, street.code, house)
        for building in buildings:
            building_files.append(building.tik_number)

# 3. Get building file details
for tik_number in building_files:
    detail = get_tik_file(siteid, tik_number)
    # Contains: addresses, gush_helka, plans, requests

# 4. Get detailed permit info for each request
for request in detail.requests:
    permit_detail = get_bakasha_file(siteid, request.request_number)
    # Contains: areas, stakeholders, events, meetings, requirements, documents
```

---

## Glossary

| Hebrew | Transliteration | English |
|--------|-----------------|---------|
| תיק בניין | Tik Binyan | Building File |
| בקשה להיתר | Bakasha L'Heter | Permit Request |
| היתר | Heter | Permit |
| גוש | Gush | Land Block |
| חלקה | Helka | Land Parcel |
| מגרש | Migrash | Plot |
| תוכנית | Tochnit | Plan |
| ועדה | Vaada | Committee |
| רשות רישוי | Rashut Rishui | Licensing Authority |
| בעלי עניין | Baalei Inyan | Stakeholders |
| מבקש | Mevakesh | Applicant |
| שטח עיקרי | Shetach Ikari | Main Area |
| שטח שירות | Shetach Sherut | Service Area |
| יחידות דיור | Yechidot Diur | Housing Units |
