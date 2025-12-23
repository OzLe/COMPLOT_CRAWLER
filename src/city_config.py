"""
City configurations for Israeli municipality Complot building permit systems.
All municipalities use the same backend (handasi.complot.co.il) with different site IDs.
"""

from dataclasses import dataclass, field
from typing import Optional
import re
from urllib.parse import urlparse, parse_qs


@dataclass
class CityConfig:
    """Configuration for a municipality's Complot system"""
    name: str                    # Hebrew city name
    name_en: str                 # English city name (for filenames)
    site_id: int                 # Complot site ID
    city_code: int               # CBS city code
    base_url: str                # City's portal URL
    street_range: tuple = (1, 2000)  # Range of street codes to scan
    api_type: str = "tikim"      # "tikim" (building files) or "bakashot" (requests)
    extra_params: dict = field(default_factory=dict)


# Known city configurations
CITIES = {
    "ofaqim": CityConfig(
        name="אופקים",
        name_en="ofaqim",
        site_id=67,
        city_code=31,
        base_url="https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx",
        street_range=(1, 1000),
        api_type="tikim"
    ),
    "batyam": CityConfig(
        name="בת ים",
        name_en="batyam",
        site_id=81,
        city_code=6200,
        base_url="https://batyam.complot.co.il/iturbakashot/",
        street_range=(1, 2000),
        api_type="bakashot"  # Bat Yam uses requests/bakashot system
    ),
    "ashkelon": CityConfig(
        name="אשקלון",
        name_en="ashkelon",
        site_id=66,
        city_code=7100,
        base_url="https://ashkelon.complot.co.il/",
        street_range=(1, 2000),
        api_type="tikim"
    ),
    "beersheva": CityConfig(
        name="באר שבע",
        name_en="beersheva",
        site_id=68,
        city_code=9000,
        base_url="https://br7.complot.co.il/",
        street_range=(1, 3000),
        api_type="tikim"
    ),
    "rehovot": CityConfig(
        name="רחובות",
        name_en="rehovot",
        site_id=80,
        city_code=8400,
        base_url="https://rechovot.complot.co.il/",
        street_range=(1, 2000),
        api_type="tikim"
    ),
    "modiin": CityConfig(
        name="מודיעין",
        name_en="modiin",
        site_id=75,
        city_code=1200,
        base_url="https://modiin.complot.co.il/",
        street_range=(1, 1000),
        api_type="tikim"
    ),
}


def parse_url_config(url: str) -> Optional[CityConfig]:
    """
    Parse a Complot URL to extract city configuration.

    Example URLs:
    - https://ofaqim.complot.co.il/newengine/Pages/buildings2.aspx#building/389000400
    - https://batyam.complot.co.il/iturbakashot/#search/GetBakashotByAddress&siteid=81&...
    """
    parsed = urlparse(url)

    # Extract city from subdomain
    host_parts = parsed.netloc.split('.')
    if len(host_parts) >= 3 and 'complot' in host_parts:
        city_subdomain = host_parts[0]
    else:
        return None

    # Try to find in known cities
    for key, config in CITIES.items():
        if key == city_subdomain or config.name_en == city_subdomain:
            return config

    # Try to extract from URL parameters
    # Parse hash fragment for params
    fragment = parsed.fragment
    params = {}

    if '&' in fragment:
        # Parse fragment as query string
        param_str = fragment.split('/', 1)[-1] if '/' in fragment else fragment
        for part in param_str.split('&'):
            if '=' in part:
                k, v = part.split('=', 1)
                params[k] = v

    # Also try query string
    query_params = parse_qs(parsed.query)
    for k, v in query_params.items():
        params[k] = v[0] if isinstance(v, list) else v

    site_id = params.get('siteid') or params.get('siteId')
    city_code = params.get('c')

    if site_id:
        # Create config from URL
        api_type = "bakashot" if "bakashot" in url.lower() or "bakash" in url.lower() else "tikim"
        return CityConfig(
            name=city_subdomain,
            name_en=city_subdomain,
            site_id=int(site_id),
            city_code=int(city_code) if city_code else 0,
            base_url=f"https://{parsed.netloc}/",
            api_type=api_type
        )

    return None


def get_city_config(city_or_url: str) -> CityConfig:
    """
    Get city configuration from city name or URL.

    Args:
        city_or_url: City name (e.g., "batyam") or full Complot URL

    Returns:
        CityConfig for the specified city

    Raises:
        ValueError if city not found
    """
    # Check if it's a URL
    if city_or_url.startswith('http'):
        config = parse_url_config(city_or_url)
        if config:
            return config
        raise ValueError(f"Could not parse configuration from URL: {city_or_url}")

    # Try as city name
    city_key = city_or_url.lower().replace(' ', '').replace('-', '')

    if city_key in CITIES:
        return CITIES[city_key]

    # Try to match by Hebrew name
    for key, config in CITIES.items():
        if config.name == city_or_url:
            return config

    raise ValueError(f"Unknown city: {city_or_url}. Available cities: {', '.join(CITIES.keys())}")


def list_cities() -> list[dict]:
    """List all known city configurations"""
    return [
        {
            "key": key,
            "name": config.name,
            "name_en": config.name_en,
            "site_id": config.site_id,
            "city_code": config.city_code
        }
        for key, config in CITIES.items()
    ]


if __name__ == "__main__":
    print("Available cities:")
    print("-" * 60)
    for city in list_cities():
        print(f"  {city['key']:15} | {city['name']:12} | site_id={city['site_id']:3} | city_code={city['city_code']}")
