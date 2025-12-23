#!/usr/bin/env python3
"""
Analyze a city's Complot API endpoints by capturing network requests.
"""

import asyncio
import json
import sys
from playwright.async_api import async_playwright
from urllib.parse import urlparse, parse_qs

async def analyze_city_api(url: str):
    """Capture and analyze API requests for a city's Complot portal"""

    api_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        async def handle_request(request):
            req_url = request.url
            if 'mgrqispi.dll' in req_url or 'magicscripts' in req_url:
                parsed = urlparse(req_url)
                params = parse_qs(parsed.query)
                api_requests.append({
                    'url': req_url,
                    'method': request.method,
                    'params': {k: v[0] if len(v) == 1 else v for k, v in params.items()},
                    'post_data': request.post_data
                })

        async def handle_response(response):
            req_url = response.url
            if 'mgrqispi.dll' in req_url:
                try:
                    body = await response.text()
                    for req in api_requests:
                        if req['url'] == req_url:
                            req['response_preview'] = body[:1000]
                            req['status'] = response.status
                            break
                except:
                    pass

        page.on('request', handle_request)
        page.on('response', handle_response)

        print(f"Loading: {url}")
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)

        # Try to extract site configuration from page
        config = await page.evaluate('''() => {
            return {
                siteBaseURL: typeof siteBaseURL !== 'undefined' ? siteBaseURL : null,
                xpaBaseURL: typeof xpaBaseURL !== 'undefined' ? xpaBaseURL : null,
                siteid: typeof siteid !== 'undefined' ? siteid : null,
                yeshuvCode: typeof yeshuvCode !== 'undefined' ? yeshuvCode : null,
                homeURL: typeof homeURL !== 'undefined' ? homeURL : null,
            }
        }''')

        await browser.close()

    print(f"\n{'='*60}")
    print("SITE CONFIGURATION")
    print(f"{'='*60}")
    for key, value in config.items():
        if value:
            print(f"  {key}: {value}")

    print(f"\n{'='*60}")
    print(f"API REQUESTS CAPTURED ({len(api_requests)})")
    print(f"{'='*60}")

    for i, req in enumerate(api_requests):
        print(f"\n--- Request {i+1} ---")
        print(f"Program: {req['params'].get('prgname', 'N/A')}")
        print(f"Site ID: {req['params'].get('siteid', 'N/A')}")
        print(f"Params: {json.dumps(req['params'], ensure_ascii=False)}")
        if 'response_preview' in req:
            preview = req['response_preview'][:300].replace('\n', ' ')
            print(f"Response: {preview}...")

    return {'config': config, 'requests': api_requests}

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://batyam.complot.co.il/iturbakashot/"
    asyncio.run(analyze_city_api(url))
