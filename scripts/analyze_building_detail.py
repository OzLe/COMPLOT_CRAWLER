#!/usr/bin/env python3
"""
Analyze the building detail page to discover API endpoints
"""

import asyncio
import json
from playwright.async_api import async_playwright

async def analyze_building_detail():
    """Capture network requests when loading a building detail page"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Store captured requests
        api_requests = []

        # Listen for all requests
        async def handle_request(request):
            url = request.url
            method = request.method
            # Filter for API-like requests
            if any(keyword in url.lower() for keyword in ['api', 'handler', 'service', 'ashx', 'json', 'building', 'tik']):
                api_requests.append({
                    'url': url,
                    'method': method,
                    'post_data': request.post_data if method == 'POST' else None,
                    'headers': dict(request.headers)
                })

        # Listen for responses
        async def handle_response(response):
            url = response.url
            if any(keyword in url.lower() for keyword in ['api', 'handler', 'service', 'ashx', 'json', 'building', 'tik']):
                try:
                    content_type = response.headers.get('content-type', '')
                    if 'json' in content_type or 'javascript' in content_type or 'text' in content_type:
                        body = await response.text()
                        for req in api_requests:
                            if req['url'] == url:
                                req['response_preview'] = body[:2000] if len(body) > 2000 else body
                                req['response_length'] = len(body)
                                break
                except Exception as e:
                    pass

        page.on('request', handle_request)
        page.on('response', handle_response)

        # Test with a known tik number
        test_tik = "389000400"
        url = f"https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx#building/{test_tik}"

        print(f"Loading: {url}")
        await page.goto(url, wait_until='networkidle', timeout=60000)

        # Wait a bit more for any delayed requests
        await asyncio.sleep(3)

        # Take a screenshot
        await page.screenshot(path='building_detail_screenshot.png', full_page=True)

        # Try to extract any visible data from the page
        page_content = await page.content()

        # Look for any data tables or detail panels
        visible_text = await page.evaluate('''() => {
            const texts = [];
            // Get main content areas
            document.querySelectorAll('table, .detail, .info, [class*="grid"], [class*="data"]').forEach(el => {
                if (el.innerText.trim()) {
                    texts.push(el.innerText.substring(0, 500));
                }
            });
            return texts;
        }''')

        await browser.close()

        print(f"\n=== Captured {len(api_requests)} API requests ===\n")

        for i, req in enumerate(api_requests):
            print(f"--- Request {i+1} ---")
            print(f"URL: {req['url']}")
            print(f"Method: {req['method']}")
            if req['post_data']:
                print(f"POST data: {req['post_data'][:500]}")
            if 'response_preview' in req:
                print(f"Response ({req['response_length']} chars): {req['response_preview'][:500]}...")
            print()

        # Save full results
        with open('building_api_analysis.json', 'w', encoding='utf-8') as f:
            json.dump({
                'test_url': url,
                'requests': api_requests,
                'visible_text_samples': visible_text[:10] if visible_text else []
            }, f, ensure_ascii=False, indent=2)

        print("\nResults saved to building_api_analysis.json")
        print("Screenshot saved to building_detail_screenshot.png")

        return api_requests

if __name__ == "__main__":
    asyncio.run(analyze_building_detail())
