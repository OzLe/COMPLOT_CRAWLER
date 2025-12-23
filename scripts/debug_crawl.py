"""
Debug script to inspect the page structure and find the actual data loading mechanism.
Run with: python debug_crawl.py
"""

import asyncio
from playwright.async_api import async_playwright


async def debug_page():
    url = "https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx#search/GetTikimByAddress&siteid=67&c=31&s=389&h=4&l=true&arguments=siteid,c,s,h,l"

    async with async_playwright() as p:
        # Launch browser (set headless=False to see what's happening)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            locale="he-IL",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        # Capture all network requests
        requests_log = []
        responses_log = []

        page.on("request", lambda req: requests_log.append({
            "url": req.url,
            "method": req.method,
            "post_data": req.post_data
        }))

        async def handle_response(response):
            try:
                content_type = response.headers.get("content-type", "")
                body = None
                if "json" in content_type or "xml" in content_type or "text" in content_type:
                    try:
                        body = await response.text()
                        if len(body) > 1000:
                            body = body[:1000] + "..."
                    except:
                        pass
                responses_log.append({
                    "url": response.url,
                    "status": response.status,
                    "content_type": content_type,
                    "body_preview": body
                })
            except:
                pass

        page.on("response", handle_response)

        print("Navigating to page...")
        await page.goto(url, wait_until="domcontentloaded")

        print("Waiting for network idle...")
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except:
            print("Network didn't become idle, continuing...")

        # Extra wait for any delayed AJAX
        await asyncio.sleep(5)

        # Dump page structure
        print("\n" + "="*60)
        print("PAGE ANALYSIS")
        print("="*60)

        # Get page title
        title = await page.title()
        print(f"\nTitle: {title}")

        # Check for iframes
        frames = page.frames
        print(f"\nFrames found: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  Frame {i}: {frame.url}")

        # Look for ExtJS components
        ext_info = await page.evaluate("""
            () => {
                const info = {
                    hasExt: typeof Ext !== 'undefined',
                    hasExtNet: typeof Ext !== 'undefined' && typeof Ext.net !== 'undefined',
                    stores: [],
                    grids: [],
                    panels: []
                };

                if (info.hasExt) {
                    // Get all component IDs
                    if (Ext.ComponentQuery) {
                        const grids = Ext.ComponentQuery.query('grid');
                        info.grids = grids.map(g => ({
                            id: g.id,
                            title: g.title,
                            rowCount: g.store ? g.store.getCount() : 0
                        }));

                        const panels = Ext.ComponentQuery.query('panel');
                        info.panels = panels.map(p => ({
                            id: p.id,
                            title: p.title
                        })).slice(0, 10);  // Limit
                    }

                    // Get stores
                    if (Ext.data && Ext.data.StoreManager) {
                        const stores = Ext.data.StoreManager.getAll();
                        info.stores = stores.map(s => ({
                            id: s.storeId,
                            count: s.getCount(),
                            data: s.getCount() > 0 ? s.getAt(0).data : null
                        })).filter(s => s.count > 0);
                    }
                }

                return info;
            }
        """)

        print(f"\nExtJS present: {ext_info.get('hasExt')}")
        print(f"Ext.NET present: {ext_info.get('hasExtNet')}")

        if ext_info.get("stores"):
            print(f"\nExt Stores with data:")
            for store in ext_info["stores"]:
                print(f"  - {store['id']}: {store['count']} records")
                if store.get("data"):
                    print(f"    Sample: {store['data']}")

        if ext_info.get("grids"):
            print(f"\nExt Grids:")
            for grid in ext_info["grids"]:
                print(f"  - {grid['id']}: {grid.get('title', 'no title')} ({grid['rowCount']} rows)")

        # Print interesting network requests
        print("\n" + "="*60)
        print("INTERESTING NETWORK REQUESTS")
        print("="*60)

        keywords = ['gettik', 'search', 'api', 'data', 'building', 'address', 'direct']
        for req in requests_log:
            url_lower = req["url"].lower()
            if any(kw in url_lower for kw in keywords):
                print(f"\n{req['method']} {req['url']}")
                if req.get("post_data"):
                    print(f"  POST data: {req['post_data'][:500]}")

        print("\n" + "="*60)
        print("API RESPONSES")
        print("="*60)

        for resp in responses_log:
            url_lower = resp["url"].lower()
            if any(kw in url_lower for kw in keywords) or "json" in resp.get("content_type", ""):
                print(f"\n{resp['status']} {resp['url']}")
                print(f"  Content-Type: {resp.get('content_type')}")
                if resp.get("body_preview"):
                    print(f"  Body: {resp['body_preview'][:500]}")

        # Take screenshot
        await page.screenshot(path="debug_screenshot.png", full_page=True)
        print("\nScreenshot saved to debug_screenshot.png")

        # Keep browser open for manual inspection
        print("\n" + "="*60)
        print("Browser is open for manual inspection.")
        print("Press Enter to close...")
        input()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug_page())
