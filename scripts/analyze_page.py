"""
Analyze the page structure and find the actual data loading mechanism.
"""

import asyncio
import json
from playwright.async_api import async_playwright


async def analyze_page():
    url = "https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx#search/GetTikimByAddress&siteid=67&c=31&s=389&h=4&l=true&arguments=siteid,c,s,h,l"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
                    except:
                        pass
                responses_log.append({
                    "url": response.url,
                    "status": response.status,
                    "content_type": content_type,
                    "body": body
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

        title = await page.title()
        print(f"\nTitle: {title}")

        # Check for iframes
        frames = page.frames
        print(f"\nFrames found: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  Frame {i}: {frame.url[:100]}")

        # Look for ExtJS components
        ext_info = await page.evaluate("""
            () => {
                const info = {
                    hasExt: typeof Ext !== 'undefined',
                    hasExtNet: typeof Ext !== 'undefined' && typeof Ext.net !== 'undefined',
                    stores: [],
                    grids: [],
                    panels: [],
                    directMethods: []
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
                            title: p.title,
                            html: p.body ? p.body.dom.innerHTML.substring(0, 200) : null
                        })).filter(p => p.html).slice(0, 5);
                    }

                    // Get stores
                    if (Ext.data && Ext.data.StoreManager) {
                        const stores = Ext.data.StoreManager.getAll();
                        info.stores = stores.map(s => ({
                            id: s.storeId,
                            count: s.getCount(),
                            data: s.getCount() > 0 ? s.getData().items.slice(0, 3).map(item => item.data) : null
                        })).filter(s => s.count > 0);
                    }
                }

                // Look for Direct methods (Ext.NET specific)
                if (typeof App !== 'undefined') {
                    info.appDefined = true;
                    info.appKeys = Object.keys(App || {}).slice(0, 20);
                }

                // Look for global DirectMethods
                if (typeof DirectMethods !== 'undefined') {
                    info.directMethods = Object.keys(DirectMethods || {});
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
                    print(f"    Sample: {json.dumps(store['data'], ensure_ascii=False, indent=2)[:500]}")

        if ext_info.get("grids"):
            print(f"\nExt Grids:")
            for grid in ext_info["grids"]:
                print(f"  - {grid['id']}: {grid.get('title', 'no title')} ({grid['rowCount']} rows)")

        if ext_info.get("appKeys"):
            print(f"\nApp object keys: {ext_info['appKeys']}")

        if ext_info.get("directMethods"):
            print(f"\nDirectMethods: {ext_info['directMethods']}")

        # Print interesting network requests
        print("\n" + "="*60)
        print("INTERESTING NETWORK REQUESTS")
        print("="*60)

        keywords = ['gettik', 'search', 'api', 'data', 'building', 'address', 'direct', 'handler']
        for req in requests_log:
            url_lower = req["url"].lower()
            if any(kw in url_lower for kw in keywords):
                print(f"\n{req['method']} {req['url'][:150]}")
                if req.get("post_data"):
                    print(f"  POST data: {req['post_data'][:1000]}")

        print("\n" + "="*60)
        print("API/JSON RESPONSES")
        print("="*60)

        for resp in responses_log:
            url_lower = resp["url"].lower()
            ct = resp.get("content_type", "")
            if (any(kw in url_lower for kw in keywords) or "json" in ct) and resp.get("body"):
                print(f"\n{resp['status']} {resp['url'][:150]}")
                print(f"  Content-Type: {ct}")
                body = resp['body']
                if body:
                    print(f"  Body ({len(body)} chars): {body[:1000]}")

        # Get the page HTML to see structure
        html_content = await page.content()

        # Take screenshot
        await page.screenshot(path="debug_screenshot.png", full_page=True)
        print("\nScreenshot saved to debug_screenshot.png")

        # Save all captured data
        with open("network_log.json", "w", encoding="utf-8") as f:
            json.dump({
                "requests": requests_log,
                "responses": [r for r in responses_log if r.get("body")]
            }, f, ensure_ascii=False, indent=2)
        print("Network log saved to network_log.json")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(analyze_page())
