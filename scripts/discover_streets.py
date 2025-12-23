"""
Discover all valid street codes by testing ranges.
Then use those to crawl the entire city.
"""

import asyncio
import json
from datetime import datetime

import httpx
from bs4 import BeautifulSoup


API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"


async def test_street(client: httpx.AsyncClient, siteid: int, c: int, s: int) -> dict | None:
    """Test if a street code returns any results by trying multiple house numbers."""

    # Try several house numbers since not all streets start at 1
    house_numbers_to_try = [1, 2, 3, 4, 5, 10, 20, 50]

    for h in house_numbers_to_try:
        url = (
            f"{API_BASE}?appname=cixpa&prgname=GetTikimByAddress"
            f"&siteid={siteid}&c={c}&s={s}&h={h}&l=true&arguments=siteid,c,s,h,l"
        )

        try:
            response = await client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text()

            # Check for results - look for the count text
            if "נמצאו" in text and "תיקי בניין" in text:
                # Extract street name from any result
                table = soup.find("table", {"id": "results-table"})
                if table:
                    tbody = table.find("tbody")
                    rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]
                    if rows:
                        cells = rows[0].find_all("td")
                        if len(cells) > 2:
                            address = cells[2].get_text(strip=True)
                            # Extract street name (address format: "STREET NUM CITY")
                            parts = address.rsplit(" ", 2)
                            street_name = parts[0] if len(parts) >= 2 else address
                            return {"code": s, "name": street_name, "sample_house": h}
        except Exception as e:
            continue

    return None


async def discover_streets(
    siteid: int = 67,
    c: int = 31,
    start: int = 1,
    end: int = 1000,
    concurrent: int = 10
) -> list[dict]:
    """
    Discover all valid street codes in a range.

    Args:
        siteid: Site ID (67 for Ofakim)
        c: City code (31)
        start: Starting street code
        end: Ending street code
        concurrent: Max concurrent requests
    """
    valid_streets = []
    semaphore = asyncio.Semaphore(concurrent)

    async def test_with_semaphore(client, s):
        async with semaphore:
            result = await test_street(client, siteid, c, s)
            if result:
                print(f"  Found street {s}: {result['name']}")
            return result

    print(f"Discovering streets from {start} to {end}...")
    print(f"Using {concurrent} concurrent connections")
    print("Testing multiple house numbers per street...")

    async with httpx.AsyncClient(timeout=30) as client:
        tasks = [test_with_semaphore(client, s) for s in range(start, end + 1)]

        # Process in batches for progress reporting
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    valid_streets.append(result)

            progress = min(i + batch_size, len(tasks))
            print(f"Progress: {progress}/{len(tasks)} ({len(valid_streets)} streets found)")

    return valid_streets


async def main():
    print("=" * 60)
    print("STREET DISCOVERY FOR OFAKIM")
    print("=" * 60)

    # Discover streets
    streets = await discover_streets(
        siteid=67,
        c=31,
        start=1,
        end=1000,
        concurrent=10  # Be gentle on the server
    )

    # Save discovered streets
    output = {
        "discovered_at": datetime.now().isoformat(),
        "siteid": 67,
        "city_code": 31,
        "total_streets": len(streets),
        "streets": sorted(streets, key=lambda x: x["code"])
    }

    with open("discovered_streets.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"DISCOVERY COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total streets found: {len(streets)}")
    print(f"Saved to discovered_streets.json")

    # Print summary
    print(f"\nStreets found:")
    for street in sorted(streets, key=lambda x: x["code"]):
        print(f"  {street['code']}: {street['name']}")


if __name__ == "__main__":
    asyncio.run(main())
