"""
Verification Experiment: Can Playwright bypass GetTikFile API block?

This script tests whether browser automation can access building details
that are blocked when using direct HTTP requests.

Tests:
1. Browser Behavior - Does the web UI show building details?
2. Session Cookies - Do browser cookies unlock the API?
3. Network Discovery - Are there alternative/hidden endpoints?

Run: python -m src.research.browser_test
"""

import asyncio
import aiohttp
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

console = Console()

# Test configuration
TEST_CITIES = [
    {
        "name": "ofaqim",
        "site_id": 67,
        "city_code": 31,
        "base_url": "https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx",
        "test_street": 150,
        "test_tik": "930008800"  # Known tik from earlier testing
    },
    {
        "name": "ramathasharon",
        "site_id": 118,
        "city_code": 2650,
        "base_url": "https://ramathasharon.complot.co.il/",
        "test_street": 101,
        "test_tik": "1423"
    }
]

API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"


class VerificationResults:
    """Store and display test results"""
    def __init__(self):
        self.results = []

    def add(self, test_name: str, city: str, passed: bool, details: str):
        self.results.append({
            "test": test_name,
            "city": city,
            "passed": passed,
            "details": details
        })

    def display(self):
        table = Table(title="Verification Experiment Results")
        table.add_column("Test", style="cyan")
        table.add_column("City", style="magenta")
        table.add_column("Result", style="green")
        table.add_column("Details", style="white")

        for r in self.results:
            status = "[green]PASS[/green]" if r["passed"] else "[red]FAIL[/red]"
            table.add_row(r["test"], r["city"], status, r["details"])

        console.print(table)


async def test_direct_api(city: dict) -> tuple[bool, str]:
    """
    Baseline test: Confirm API is blocked with direct HTTP request.
    """
    url = f"{API_BASE}?appname=cixpa&prgname=GetTikFile&siteid={city['site_id']}&t={city['test_tik']}&arguments=siteid,t"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            html = await resp.text()

            if "לא ניתן להציג" in html:
                return False, "API blocked (as expected)"
            elif "result-title-div-id" in html or "#info-main" in html:
                return True, "API returned data!"
            else:
                return False, f"Unknown response (status: {resp.status})"


async def test_browser_access(city: dict) -> tuple[bool, str]:
    """
    Test 1: Can a browser access building details through the web UI?

    This test:
    1. Opens the building search page in a real browser
    2. Monitors network requests for GetTikFile calls
    3. Checks if GetTikFile succeeds in browser context
    """
    console.print(f"\n[cyan]Test 1: Browser Access for {city['name']}[/cyan]")

    api_calls = []
    api_responses = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Capture all API requests and responses
        async def handle_request(request):
            if "mgrqispi" in request.url or "handasi.complot.co.il" in request.url:
                api_calls.append({
                    "url": request.url,
                    "method": request.method
                })

        async def handle_response(response):
            if "GetTikFile" in response.url:
                try:
                    body = await response.text()
                    success = "result-title-div-id" in body or "#info-main" in body
                    blocked = "לא ניתן להציג" in body
                    api_responses.append({
                        "url": response.url,
                        "status": response.status,
                        "success": success,
                        "blocked": blocked
                    })
                except:
                    pass

        page.on("request", handle_request)
        page.on("response", handle_response)

        # Navigate to the building search page
        console.print(f"  Navigating to {city['base_url']}...")
        try:
            await page.goto(city['base_url'], timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            console.print(f"  [yellow]Warning: Page load timeout (continuing anyway)[/yellow]")

        # Try to directly access GetTikFile via page.evaluate (JavaScript context)
        console.print(f"  Testing GetTikFile from browser context...")
        tik_url = f"{API_BASE}?appname=cixpa&prgname=GetTikFile&siteid={city['site_id']}&t={city['test_tik']}&arguments=siteid,t"

        try:
            response = await page.request.get(tik_url)
            body = await response.text()

            if "לא ניתן להציג" in body:
                result = (False, "GetTikFile blocked even in browser context")
            elif "result-title-div-id" in body or "#info-main" in body:
                result = (True, "GetTikFile WORKS in browser context!")
            else:
                result = (False, f"Unknown response (status {response.status})")
        except Exception as e:
            result = (False, f"Error: {str(e)}")

        await browser.close()

        # Report captured API calls
        console.print(f"  Captured {len(api_calls)} API calls")
        for call in api_calls[:5]:  # Show first 5
            console.print(f"    - {call['method']} {call['url'][:80]}...")

        return result


async def test_session_cookies(city: dict) -> tuple[bool, str]:
    """
    Test 2: Do session cookies from browser unlock the API?

    This test:
    1. Opens the site in browser to get session cookies
    2. Extracts cookies from browser context
    3. Uses those cookies in direct aiohttp request
    4. Checks if GetTikFile works with browser cookies
    """
    console.print(f"\n[cyan]Test 2: Session Cookies for {city['name']}[/cyan]")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Visit the site to get session cookies
        console.print(f"  Visiting site to capture cookies...")
        try:
            await page.goto(city['base_url'], timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass

        # Extract cookies
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}

        console.print(f"  Captured {len(cookies)} cookies:")
        for name in list(cookie_dict.keys())[:5]:
            console.print(f"    - {name}")

        await browser.close()

    # Now test API with these cookies
    console.print(f"  Testing API with browser cookies...")

    url = f"{API_BASE}?appname=cixpa&prgname=GetTikFile&siteid={city['site_id']}&t={city['test_tik']}&arguments=siteid,t"

    # Create cookie header
    cookie_header = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

    headers = {
        "Cookie": cookie_header,
        "Referer": city['base_url'],
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            html = await resp.text()

            if "לא ניתן להציג" in html:
                return False, "API still blocked with browser cookies"
            elif "result-title-div-id" in html or "#info-main" in html:
                return True, "API WORKS with browser cookies!"
            else:
                return False, f"Unknown response (status: {resp.status})"


async def discover_endpoints(city: dict) -> tuple[bool, list]:
    """
    Test 3: Are there alternative API endpoints?

    This test:
    1. Opens the site in browser
    2. Monitors ALL network traffic
    3. Looks for any API calls that might be alternatives to GetTikFile
    """
    console.print(f"\n[cyan]Test 3: Endpoint Discovery for {city['name']}[/cyan]")

    discovered_endpoints = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Capture all requests
        def handle_request(request):
            url = request.url
            # Look for any API-like endpoints
            if any(pattern in url.lower() for pattern in [
                "mgrqispi", "api", "service", "handler",
                "getbuilding", "gettik", "getbakash", "data"
            ]):
                if url not in [e['url'] for e in discovered_endpoints]:
                    discovered_endpoints.append({
                        "url": url,
                        "method": request.method
                    })

        page.on("request", handle_request)

        # Navigate and wait for network activity
        console.print(f"  Monitoring network traffic...")
        try:
            await page.goto(city['base_url'], timeout=30000)
            await page.wait_for_load_state("networkidle", timeout=15000)
        except:
            pass

        # Try clicking around to trigger more API calls
        console.print(f"  Interacting with page...")
        try:
            # Look for any clickable elements that might load building data
            links = await page.locator("a").all()
            for link in links[:5]:  # Try first 5 links
                try:
                    href = await link.get_attribute("href")
                    if href and "building" in str(href).lower():
                        console.print(f"    Found building link: {href[:50]}...")
                except:
                    pass
        except:
            pass

        await browser.close()

    # Report discovered endpoints
    console.print(f"  Discovered {len(discovered_endpoints)} endpoints:")

    # Filter for unique and interesting endpoints
    unique_programs = set()
    for ep in discovered_endpoints:
        url = ep['url']
        if "prgname=" in url:
            # Extract program name
            import re
            match = re.search(r'prgname=(\w+)', url)
            if match:
                unique_programs.add(match.group(1))

    for prog in sorted(unique_programs):
        console.print(f"    - {prog}")

    # Check if we found any new endpoints (not GetTikFile/GetTikimByAddress)
    known = {"GetTikFile", "GetTikimByAddress", "GetBakashotByAddress", "GetBakashaFile"}
    new_endpoints = unique_programs - known

    if new_endpoints:
        return True, list(new_endpoints)
    else:
        return False, list(unique_programs)


async def main():
    """Run all verification tests"""
    console.print("\n" + "=" * 70)
    console.print("[bold cyan]PLAYWRIGHT VERIFICATION EXPERIMENT[/bold cyan]")
    console.print("Testing if browser automation can bypass GetTikFile API block")
    console.print("=" * 70)

    results = VerificationResults()

    for city in TEST_CITIES:
        console.print(f"\n[bold magenta]Testing {city['name'].upper()}[/bold magenta]")
        console.print("-" * 50)

        # Baseline: Confirm API is blocked
        console.print("\n[cyan]Baseline: Direct API Test[/cyan]")
        passed, details = await test_direct_api(city)
        results.add("Direct API", city['name'], passed, details)
        console.print(f"  Result: {'PASS' if passed else 'FAIL'} - {details}")

        # Test 1: Browser access
        passed, details = await test_browser_access(city)
        results.add("Browser Access", city['name'], passed, details)
        console.print(f"  Result: {'PASS' if passed else 'FAIL'} - {details}")

        # Test 2: Session cookies
        passed, details = await test_session_cookies(city)
        results.add("Session Cookies", city['name'], passed, details)
        console.print(f"  Result: {'PASS' if passed else 'FAIL'} - {details}")

        # Test 3: Endpoint discovery
        found_new, endpoints = await discover_endpoints(city)
        details = f"Found: {', '.join(endpoints)}" if endpoints else "No endpoints found"
        results.add("New Endpoints", city['name'], found_new, details)

    # Display summary
    console.print("\n" + "=" * 70)
    console.print("[bold cyan]SUMMARY[/bold cyan]")
    console.print("=" * 70)
    results.display()

    # Conclusion
    console.print("\n[bold]CONCLUSION:[/bold]")
    all_failed = all(not r['passed'] for r in results.results)

    if all_failed:
        console.print("[red]All tests FAILED - Browser automation cannot bypass API block[/red]")
        console.print("The blocking is at the API level (server-side policy)")
        console.print("Recommendation: Do NOT implement Playwright integration")
    else:
        console.print("[green]Some tests PASSED - Browser workaround may be possible![/green]")
        console.print("Recommendation: Investigate further and implement browser integration")

    return results


if __name__ == "__main__":
    asyncio.run(main())
