"""
Crawler for ofaqim.complot.co.il building permit data.

This script uses Playwright to crawl the building permit system,
which requires JavaScript execution to load data.

URL pattern: #search/GetTikimByAddress&siteid=67&c=31&s=389&h=4&l=true
Parameters:
  - siteid: Site ID (67 for Ofakim)
  - c: City/Council code
  - s: Street code
  - h: House number
  - l: Unknown flag (true/false)
"""

import asyncio
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout


@dataclass
class CrawlParams:
    siteid: int = 67
    c: int = 31  # city/council code
    s: int = 389  # street code
    h: int = 4  # house number
    l: bool = True


class BuildingPermitCrawler:
    BASE_URL = "https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx"

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.results = []

    def _build_url(self, params: CrawlParams) -> str:
        """Build the full URL with hash parameters."""
        l_str = "true" if params.l else "false"
        hash_part = f"#search/GetTikimByAddress&siteid={params.siteid}&c={params.c}&s={params.s}&h={params.h}&l={l_str}&arguments=siteid,c,s,h,l"
        return f"{self.BASE_URL}{hash_part}"

    async def _wait_for_data(self, page: Page, timeout: int = 30000):
        """Wait for dynamic content to load."""
        # Wait for network to be idle (no requests for 500ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
        except PlaywrightTimeout:
            print("Network idle timeout - continuing anyway")

        # Wait for potential data containers
        selectors_to_try = [
            ".x-grid",  # ExtJS grid
            ".x-panel-body",  # ExtJS panel
            "[class*='result']",
            "[class*='data']",
            "table",
        ]

        for selector in selectors_to_try:
            try:
                await page.wait_for_selector(selector, timeout=5000)
                print(f"Found element: {selector}")
            except PlaywrightTimeout:
                pass

    async def _extract_data(self, page: Page) -> dict:
        """Extract data from the loaded page."""
        data = {
            "url": page.url,
            "title": await page.title(),
            "tables": [],
            "grids": [],
            "text_content": [],
        }

        # Extract table data
        tables = await page.query_selector_all("table")
        for i, table in enumerate(tables):
            rows = await table.query_selector_all("tr")
            table_data = []
            for row in rows:
                cells = await row.query_selector_all("td, th")
                row_data = [await cell.inner_text() for cell in cells]
                if any(row_data):  # Skip empty rows
                    table_data.append(row_data)
            if table_data:
                data["tables"].append(table_data)

        # Extract ExtJS grid data
        grids = await page.query_selector_all(".x-grid-item, .x-grid-row")
        for grid in grids:
            text = await grid.inner_text()
            if text.strip():
                data["grids"].append(text.strip())

        # Extract general panel content
        panels = await page.query_selector_all(".x-panel-body")
        for panel in panels:
            text = await panel.inner_text()
            if text.strip() and len(text.strip()) > 10:
                data["text_content"].append(text.strip())

        # Try to intercept any JSON data in the page
        try:
            json_data = await page.evaluate("""
                () => {
                    // Look for Ext stores with data
                    if (window.Ext && Ext.data && Ext.data.StoreManager) {
                        const stores = Ext.data.StoreManager.getAll();
                        return stores.map(store => ({
                            id: store.storeId,
                            data: store.getData().items.map(item => item.data)
                        }));
                    }
                    return null;
                }
            """)
            if json_data:
                data["ext_stores"] = json_data
        except Exception as e:
            print(f"Could not extract Ext stores: {e}")

        return data

    async def _intercept_network(self, page: Page):
        """Set up network interception to capture API responses."""
        api_responses = []

        async def handle_response(response):
            url = response.url
            if any(keyword in url.lower() for keyword in ['gettik', 'search', 'api', 'data', 'json']):
                try:
                    body = await response.text()
                    api_responses.append({
                        "url": url,
                        "status": response.status,
                        "body": body[:5000]  # Limit size
                    })
                    print(f"Captured API response: {url}")
                except:
                    pass

        page.on("response", handle_response)
        return api_responses

    async def crawl_single(self, params: CrawlParams) -> dict:
        """Crawl a single URL with given parameters."""
        url = self._build_url(params)
        print(f"Crawling: {url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                locale="he-IL",
                viewport={"width": 1920, "height": 1080}
            )
            page = await context.new_page()

            # Set up network interception
            api_responses = await self._intercept_network(page)

            # Navigate to the page
            await page.goto(url, wait_until="domcontentloaded")

            # Wait for dynamic content
            await self._wait_for_data(page)

            # Give extra time for AJAX requests
            await asyncio.sleep(3)

            # Extract data
            data = await self._extract_data(page)
            data["params"] = asdict(params)
            data["api_responses"] = api_responses

            # Take a screenshot for debugging
            screenshot_path = Path(f"screenshot_{params.c}_{params.s}_{params.h}.png")
            await page.screenshot(path=str(screenshot_path), full_page=True)
            data["screenshot"] = str(screenshot_path)

            await browser.close()

        return data

    async def crawl_range(
        self,
        siteid: int = 67,
        c_range: range = None,
        s_range: range = None,
        h_range: range = None,
        output_file: str = "results.json"
    ) -> list:
        """
        Crawl multiple URLs by iterating through parameter ranges.

        Args:
            siteid: Site ID (default 67 for Ofakim)
            c_range: Range of city/council codes to try
            s_range: Range of street codes to try
            h_range: Range of house numbers to try
            output_file: Where to save results
        """
        c_range = c_range or range(31, 32)
        s_range = s_range or range(389, 390)
        h_range = h_range or range(1, 11)

        all_results = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                locale="he-IL",
                viewport={"width": 1920, "height": 1080}
            )

            for c in c_range:
                for s in s_range:
                    for h in h_range:
                        params = CrawlParams(siteid=siteid, c=c, s=s, h=h)
                        url = self._build_url(params)
                        print(f"Crawling: c={c}, s={s}, h={h}")

                        page = await context.new_page()
                        api_responses = await self._intercept_network(page)

                        try:
                            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                            await self._wait_for_data(page)
                            await asyncio.sleep(2)

                            data = await self._extract_data(page)
                            data["params"] = asdict(params)
                            data["api_responses"] = api_responses

                            all_results.append(data)

                        except Exception as e:
                            print(f"Error crawling {url}: {e}")
                            all_results.append({
                                "params": asdict(params),
                                "error": str(e)
                            })

                        await page.close()

                        # Save intermediate results
                        with open(output_file, "w", encoding="utf-8") as f:
                            json.dump(all_results, f, ensure_ascii=False, indent=2)

            await browser.close()

        return all_results


async def main():
    crawler = BuildingPermitCrawler(headless=True)

    # Single crawl example
    params = CrawlParams(siteid=67, c=31, s=389, h=4, l=True)
    result = await crawler.crawl_single(params)

    # Save result
    with open("single_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("\nResult saved to single_result.json")
    print(f"Screenshot saved to {result.get('screenshot')}")

    # Print summary
    print("\n--- Summary ---")
    print(f"Tables found: {len(result.get('tables', []))}")
    print(f"Grids found: {len(result.get('grids', []))}")
    print(f"API responses captured: {len(result.get('api_responses', []))}")

    if result.get("api_responses"):
        print("\nCaptured API URLs:")
        for resp in result["api_responses"]:
            print(f"  - {resp['url']}")


if __name__ == "__main__":
    asyncio.run(main())
