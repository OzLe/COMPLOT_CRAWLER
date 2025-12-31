# Complot API Research Findings

**Date:** December 31, 2025
**Status:** Complete
**Conclusion:** Browser automation cannot bypass API restrictions

---

## Executive Summary

The Complot building permit API (`GetTikFile`) has been blocked for all Israeli municipalities. This document summarizes our comprehensive investigation into whether browser automation tools (Playwright, Scrapy) could bypass these restrictions.

**Finding:** The blocking occurs at the server-side API level. No client-side workaround exists.

---

## Background

### The Problem

The Complot Crawler extracts building permit data from Israeli municipal engineering departments. The crawler uses two main API endpoints:

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `GetTikimByAddress` | Search buildings by address | ✅ Working |
| `GetTikFile` | Get detailed building info | ❌ Blocked |

When calling `GetTikFile`, all requests return:

```
לא ניתן להציג את המידע המבוקש בהתאם לשלב הסטטוטורי
(Cannot display the requested information according to the statutory phase)
```

### Research Question

Could browser automation (Playwright/Scrapy) bypass this restriction by:
1. Executing requests in a real browser context?
2. Using session cookies from authenticated browsing?
3. Discovering alternative/hidden API endpoints?

---

## Methodology

### Phase 1: API Architecture Analysis

Examined the current implementation and website structure:

- **Frontend:** SharePoint 2013 + ExtJS (server-side rendering)
- **API:** `mgrqispi.dll` (Magic Software eDeveloper)
- **Authentication:** ASP.NET session cookies + SharePoint form digest
- **Data Loading:** Server-rendered HTML (not JavaScript/AJAX)

### Phase 2: Verification Experiment

Created `src/research/browser_test.py` with three tests:

1. **Browser Context Test** - Make API calls from within Playwright browser
2. **Session Cookie Test** - Extract browser cookies, apply to direct HTTP requests
3. **Endpoint Discovery** - Monitor network traffic for alternative APIs

### Cities Tested

| City | Site ID | Test Tik Number |
|------|---------|-----------------|
| Ofaqim | 67 | 930008800 |
| Ramat HaSharon | 118 | 1423 |

---

## Results

### Test 1: Browser Context Access

**Question:** Does making API calls from a real browser succeed?

**Method:**
```python
async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    response = await page.request.get(GetTikFile_URL)
```

**Result:** ❌ FAILED

The API returns the same error whether called from:
- Direct HTTP client (aiohttp)
- Browser context (Playwright)
- JavaScript fetch within page

### Test 2: Session Cookie Extraction

**Question:** Do browser session cookies unlock the API?

**Method:**
1. Browse to Complot site in Playwright
2. Extract all cookies from browser context
3. Apply cookies to direct HTTP request

**Cookies Captured:**
```
SPUsageId          - SharePoint usage tracking
TS013abeb3         - Traffic management
TS0146d756         - Traffic management
_ga, _gid          - Google Analytics
WSS_FullScreenMode - SharePoint UI state
```

**Result:** ❌ FAILED

API remains blocked even with full browser cookie set.

### Test 3: Hidden Endpoint Discovery

**Question:** Are there alternative API endpoints?

**Method:**
- Monitor all network traffic during browsing
- Filter for API-like patterns
- Look for undocumented endpoints

**Endpoints Found:**
```
GetTikimByAddress    - Already known (works)
GetBakashotByAddress - Already known (works)
GetTikFile           - Already known (blocked)
GetBakashaFile       - Already known (blocked)
```

**Result:** ❌ FAILED

No alternative endpoints discovered.

---

## Summary Table

| Test | Ofaqim | Ramat HaSharon | Conclusion |
|------|--------|----------------|------------|
| Direct API | ❌ Blocked | ❌ Blocked | Baseline confirmed |
| Browser Context | ❌ Blocked | ❌ Blocked | Not a client issue |
| Session Cookies | ❌ Blocked | ❌ Blocked | Not auth-related |
| Hidden Endpoints | ❌ None | ❌ None | No workaround |

---

## Technical Analysis

### Why Browser Automation Won't Help

1. **Server-Side Blocking**
   The API checks occur on the server before any response is generated. The client type (browser vs. script) is irrelevant.

2. **No JavaScript-Rendered Content**
   Building details are not loaded via AJAX. The pages use server-side rendering, so there's no hidden data to capture.

3. **Policy-Based Restriction**
   The error message mentions "statutory phase" (שלב הסטטוטורי), indicating this is an intentional policy decision, not a technical bug.

4. **Uniform Behavior**
   All cities return the same error, suggesting a platform-wide policy change by Complot.

### What Would Help (Hypothetically)

Browser automation would only help if:
- ❌ Content was JavaScript-rendered (it's not)
- ❌ Server checked for browser fingerprints (it doesn't)
- ❌ Session tokens unlocked data (they don't)
- ❌ Alternative endpoints existed (they don't)

---

## Recommendations

### Do Not Implement

- ❌ Playwright integration for data fetching
- ❌ Scrapy with browser rendering
- ❌ Session/cookie management complexity
- ❌ JavaScript execution pipelines

### Continue With

- ✅ Current aiohttp-based fetching (optimal for available data)
- ✅ Street discovery (Phase 1) - works perfectly
- ✅ Building records search (Phase 2) - works perfectly
- ✅ Automatic skip of blocked phases (3 & 4)

### Alternative Data Sources

If detailed building data is required:

1. **Contact Municipalities Directly**
   - Request API credentials
   - Ask about data sharing agreements
   - Inquire about bulk data exports

2. **Israeli Government Open Data**
   - data.gov.il
   - Municipal open data portals
   - Planning authority databases

3. **Monitor for Changes**
   - The block may be temporary
   - Set up periodic API testing
   - Check for policy announcements

---

## Files Created

```
src/research/
├── __init__.py           # Module init
├── browser_test.py       # Verification experiment script
└── README.md             # Quick reference documentation
```

### Running the Experiment

```bash
# From project root
PYTHONPATH=/Users/ozlevi/Development/crawltest python -m src.research.browser_test
```

---

## Conclusion

**Playwright and Scrapy cannot bypass the GetTikFile API block.**

The restriction is a server-side policy decision by Complot, not a technical limitation that can be circumvented. The current crawler implementation is already optimal for the data that remains accessible.

### Current Crawler Capabilities

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Street Discovery | ✅ Fully functional |
| 2 | Building Records | ✅ Fully functional |
| 3 | Building Details | ⛔ Blocked (auto-skipped) |
| 4 | Request Details | ⛔ Blocked (auto-skipped) |
| 5 | CSV Export | ✅ Exports available data |

The crawler remains valuable for collecting:
- Street names and codes
- Building file numbers (tik numbers)
- Addresses
- Gush/Helka (land parcel) information

---

*Research conducted using Playwright 1.57.0 with Chromium browser*
