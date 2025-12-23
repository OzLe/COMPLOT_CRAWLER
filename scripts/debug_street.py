"""Debug street discovery."""
import asyncio
import httpx
from bs4 import BeautifulSoup

API_BASE = "https://handasi.complot.co.il/magicscripts/mgrqispi.dll"

async def debug_street(s: int):
    url = (
        f"{API_BASE}?appname=cixpa&prgname=GetTikimByAddress"
        f"&siteid=67&c=31&s={s}&h=1&l=true&arguments=siteid,c,s,h,l"
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        print(f"Status: {response.status_code}")
        print(f"URL: {url}")

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text()

        print(f"\nText content preview:")
        print(text[:1000])

        print(f"\n'נמצאו' in text: {'נמצאו' in text}")

        table = soup.find("table", {"id": "results-table"})
        print(f"Table found: {table is not None}")

        if table:
            tbody = table.find("tbody")
            print(f"Tbody found: {tbody is not None}")
            rows = table.find_all("tr")
            print(f"Rows found: {len(rows)}")
            for i, row in enumerate(rows[:3]):
                cells = row.find_all("td")
                print(f"  Row {i}: {len(cells)} cells")
                for j, cell in enumerate(cells):
                    print(f"    Cell {j}: {cell.get_text(strip=True)[:50]}")

# Test known working street
asyncio.run(debug_street(389))
