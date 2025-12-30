#!/usr/bin/env python3
"""
Validate which cities are accessible on Complot infrastructure.
Tests subdomain access and API availability.
"""

import asyncio
import aiohttp
import re
from bs4 import BeautifulSoup

# Cities to test with potential subdomain variations
# Excluding already known: ofaqim, batyam, ashkelon, beersheva, rehovot, modiin
CITIES_TO_TEST = [
    # (Hebrew name, potential subdomains to try)
    ("אור יהודה", ["oryehuda", "or-yehuda", "orhuda"]),
    ("אור עקיבא", ["orakiva", "or-akiva", "oraqiva"]),
    ("אילת", ["eilat", "elat"]),
    ("אכסאל", ["iksal", "aksaal", "iksal"]),
    ("אשדוד", ["ashdod"]),
    ("בני ברק", ["bnei-brak", "bneibrak", "bneibraq"]),
    ("גבעתיים", ["givatayim", "givataim"]),
    ("גליל מזרחי", ["galil-mizrahi", "eastern-galilee", "galil"]),
    ("דימונה", ["dimona"]),
    ("הוד השרון", ["hodhasharon", "hod-hasharon"]),
    ("זכרון יעקב", ["zichron", "zichronyaakov", "zichron-yaakov"]),
    ("חולון", ["holon"]),
    ("חיפה", ["haifa"]),
    ("טבריה", ["tiberias", "tveria", "tverya"]),
    ("טירת הכרמל", ["tirat-hacarmel", "tirathacarmel", "tirat-carmel"]),
    ("יבנה", ["yavne", "yavneh"]),
    ("מגדל העמק", ["migdal-haemek", "migdalhaemek"]),
    ("קריית גת", ["kiryat-gat", "kiryatgat", "qiryat-gat"]),
    ("קרית אתא", ["kiryat-ata", "kiryatata", "qiryat-ata"]),
    ("קרית מלאכי", ["kiryat-malachi", "kiryatmalachi"]),
    ("ראשון לציון", ["rishon", "rishon-lezion", "rishonlezion"]),
    ("רמת השרון", ["ramat-hasharon", "ramathasharon"]),
    ("רעננה", ["raanana", "ra'anana"]),
    ("תל מונד", ["tel-mond", "telmond"]),
    ("בית שאן", ["beit-shean", "beitshean", "bet-shean"]),
    ("בית שמש", ["beit-shemesh", "beitshemesh", "bet-shemesh"]),
    ("ביתר עילית", ["beitar-illit", "beitarillit", "beitar"]),
    ("הרצליה", ["herzliya", "hertzeliya"]),
    ("טייבה", ["tayibe", "taibe", "tayba"]),
    ("יוקנעם עילית", ["yokneam", "yokneam-illit"]),
    ("כפר יונה", ["kfar-yona", "kfaryona"]),
    ("כפר סבא", ["kfar-saba", "kfarsaba", "ksaba"]),
    ("מעלה אדומים", ["maale-adumim", "maaleadumim"]),
    ("מעלות תרשיחא", ["maalot", "maalot-tarshiha"]),
    ("נצרת", ["nazareth", "natzrat", "nazerat"]),
    ("נתיבות", ["netivot"]),
    ("צפת", ["tzfat", "safed", "zfat"]),
    ("רהט", ["rahat"]),
    ("רמת גן", ["ramat-gan", "ramatgan"]),
]

async def test_subdomain(session: aiohttp.ClientSession, subdomain: str) -> dict:
    """Test if a subdomain is valid and extract site info."""
    result = {
        "subdomain": subdomain,
        "accessible": False,
        "site_id": None,
        "has_buildings_page": False,
        "has_api": False,
        "error": None
    }

    base_url = f"https://{subdomain}.complot.co.il"

    try:
        # Try main page
        async with session.get(base_url, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
            if resp.status == 200:
                result["accessible"] = True
                html = await resp.text()

                # Try to find site_id in the page
                site_id_match = re.search(r'siteid["\s:=]+(\d+)', html, re.IGNORECASE)
                if site_id_match:
                    result["site_id"] = int(site_id_match.group(1))

                # Check for buildings/engineering pages
                if "בניין" in html or "הנדסה" in html or "building" in html.lower():
                    result["has_buildings_page"] = True
            else:
                result["error"] = f"HTTP {resp.status}"
                return result

    except aiohttp.ClientConnectorError:
        result["error"] = "Connection failed"
        return result
    except asyncio.TimeoutError:
        result["error"] = "Timeout"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

    # Try common building search pages
    building_pages = [
        "/buildings/",
        "/newengine/Pages/buildings2.aspx",
        "/iturbakashot/",
        "/iturtikim/",
    ]

    for page in building_pages:
        try:
            async with session.get(f"{base_url}{page}", timeout=aiohttp.ClientTimeout(total=5), ssl=False) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # Look for site_id if not found yet
                    if not result["site_id"]:
                        site_id_match = re.search(r'siteid["\s:=]+(\d+)', html, re.IGNORECASE)
                        if site_id_match:
                            result["site_id"] = int(site_id_match.group(1))
                    result["has_buildings_page"] = True
                    break
        except:
            continue

    # If we found a site_id, test the API
    if result["site_id"]:
        try:
            api_url = f"https://handasi.complot.co.il/magicscripts/mgrqispi.dll?appname=cixpa&prgname=GetTikimByAddress&siteid={result['site_id']}&c=1&s=1&h=1&l=true&arguments=siteid,c,s,h,l"
            async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    # Check if it's a valid response (not an error page)
                    if "ERR_" not in html or "נמצאו" in html:
                        result["has_api"] = True
        except:
            pass

    return result


async def test_city(session: aiohttp.ClientSession, hebrew_name: str, subdomains: list) -> dict:
    """Test all subdomain variations for a city."""
    city_result = {
        "hebrew_name": hebrew_name,
        "working_subdomain": None,
        "site_id": None,
        "status": "not_found",
        "tested_subdomains": []
    }

    for subdomain in subdomains:
        result = await test_subdomain(session, subdomain)
        city_result["tested_subdomains"].append(result)

        if result["accessible"] and result["site_id"]:
            city_result["working_subdomain"] = subdomain
            city_result["site_id"] = result["site_id"]
            city_result["status"] = "found"
            city_result["has_api"] = result["has_api"]
            break
        elif result["accessible"]:
            # Accessible but no site_id found yet
            if not city_result["working_subdomain"]:
                city_result["working_subdomain"] = subdomain
                city_result["status"] = "partial"

    return city_result


async def main():
    print("=" * 70)
    print("COMPLOT CITY VALIDATION")
    print("=" * 70)
    print(f"Testing {len(CITIES_TO_TEST)} cities...\n")

    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        results = []

        for hebrew_name, subdomains in CITIES_TO_TEST:
            print(f"Testing: {hebrew_name} ({', '.join(subdomains)})...", end=" ", flush=True)
            result = await test_city(session, hebrew_name, subdomains)
            results.append(result)

            if result["status"] == "found":
                print(f"✓ Found: {result['working_subdomain']}.complot.co.il (site_id={result['site_id']})")
            elif result["status"] == "partial":
                print(f"~ Partial: {result['working_subdomain']}.complot.co.il (no site_id)")
            else:
                print("✗ Not found")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    found = [r for r in results if r["status"] == "found"]
    partial = [r for r in results if r["status"] == "partial"]
    not_found = [r for r in results if r["status"] == "not_found"]

    print(f"\nFound ({len(found)}):")
    for r in found:
        api_status = "✓ API works" if r.get("has_api") else "? API untested"
        print(f"  {r['hebrew_name']:<20} -> {r['working_subdomain']}.complot.co.il (site_id={r['site_id']}) {api_status}")

    if partial:
        print(f"\nPartial - accessible but no site_id ({len(partial)}):")
        for r in partial:
            print(f"  {r['hebrew_name']:<20} -> {r['working_subdomain']}.complot.co.il")

    print(f"\nNot found ({len(not_found)}):")
    for r in not_found:
        print(f"  {r['hebrew_name']}")

    # Generate config code for found cities
    if found:
        print("\n" + "=" * 70)
        print("SUGGESTED CITY CONFIGURATIONS")
        print("=" * 70)
        print("\n# Add to src/city_config.py:\n")

        for r in found:
            subdomain = r['working_subdomain']
            name_en = subdomain.replace("-", "").replace("'", "")
            print(f'''    "{name_en}": CityConfig(
        name="{r['hebrew_name']}",
        name_en="{name_en}",
        site_id={r['site_id']},
        city_code=0,  # TODO: Find CBS city code
        base_url="https://{subdomain}.complot.co.il/",
        street_range=(1, 2000),
        api_type="tikim"  # TODO: Verify API type
    ),
''')


if __name__ == "__main__":
    asyncio.run(main())
