# Browser Automation Research

## Experiment: Can Playwright Bypass GetTikFile API Block?

**Date:** December 31, 2025
**Result:** NO - Browser automation cannot bypass the block

## Summary

The Complot API (`GetTikFile`) has been blocked for all municipalities. This experiment tested whether browser automation (Playwright) could bypass this restriction.

**Conclusion:** The blocking occurs at the server-side API level, not the client/browser level. No browser-based workaround exists.

## Test Results

| Test | Result | Details |
|------|--------|---------|
| Direct API | FAIL | API blocked (baseline confirmation) |
| Browser Context | FAIL | GetTikFile blocked even when called from browser |
| Session Cookies | FAIL | Browser cookies do not unlock the API |
| Hidden Endpoints | FAIL | No alternative endpoints discovered |

## What Was Tested

### 1. Browser Context Access
Tested if making API requests from within a real browser context (with full JavaScript, cookies, and session) would succeed where direct HTTP fails.

**Finding:** The API returns the same "cannot display" error regardless of whether the request comes from a browser or direct HTTP client.

### 2. Session Cookie Extraction
Extracted session cookies from browser (including ASP.NET session, Google Analytics, and SharePoint cookies) and applied them to direct API requests.

**Finding:** Cookies do not unlock the API. The blocking is not session-based.

### 3. Network Traffic Analysis
Monitored all network requests during browser interaction to discover alternative API endpoints.

**Finding:** No alternative endpoints for fetching building details were discovered.

## Technical Details

### API Blocking Mechanism
The server returns this error for all `GetTikFile` requests:
```
לא ניתן להציג את המידע המבוקש בהתאם לשלב הסטטוטורי
(Cannot display the requested information according to the statutory phase)
```

This is a **policy-level block**, not a technical restriction that can be bypassed.

### Cookies Captured (Example)
```
SPUsageId, TS013abeb3, TS0146d756, _ga, _gid, WSS_FullScreenMode
```
None of these unlock API access.

## Recommendations

1. **Do NOT implement Playwright/Scrapy integration** - It will not help
2. **Focus on available data** - Streets and basic building records work
3. **Contact municipalities directly** if detailed data is needed
4. **Monitor for API changes** - The block may be temporary

## Running the Experiment

```bash
PYTHONPATH=/Users/ozlevi/Development/crawltest python -m src.research.browser_test
```

## Files

- `browser_test.py` - Main verification script with all tests
- `README.md` - This documentation
