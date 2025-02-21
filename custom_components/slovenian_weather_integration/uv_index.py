import aiohttp
import logging
from bs4 import BeautifulSoup
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# URL za pridobitev UV indeksa (Temis)
BASE_UV_URL = "https://www.temis.nl/uvradiation/nrt/uvindex.php"

async def fetch_uv_index(lat: float, lon: float) -> float | None:
    """Asinhrono pridobi trenutni UV indeks za dano lat in lon.

    Funkcija skuša preskočiti morebitne vrstice s tekstovnimi vrednostmi in vrne prvo veljavno numerično vrednost.
    """
    url = f"{BASE_UV_URL}?lon={lon}&lat={lat}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching UV index: HTTP %s", response.status)
                    return None
                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")
                tables = soup.find_all("table")
                if not tables:
                    _LOGGER.error("No tables found in UV index page")
                    return None
                for table in tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            uv_str = cols[1].get_text(strip=True)
                            try:
                                uv = float(uv_str)
                                return uv
                            except ValueError:
                                continue
                _LOGGER.error("No valid UV index found in page")
                return None
    except Exception as e:
        _LOGGER.error("Exception fetching UV index: %s", e)
        return None

async def fetch_location_coords(location: str, locations_url: str) -> tuple[float, float] | None:
    """
    Asinhrono pridobi koordinate (lat, lon) za dano lokacijo iz JSON-ja, ki ga vrne LOCATIONS_URL.
    
    Pričakuje se, da je v polju 'features' in da ima vsak element 'properties' z 'title'
    ter 'geometry' z 'coordinates' ([lon, lat]).
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(locations_url) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching locations: HTTP %s", response.status)
                    return None
                data = await response.json()
                for feature in data.get("features", []):
                    props = feature.get("properties", {})
                    title = props.get("title", "")
                    if title.lower() == location.lower():
                        coords = feature.get("geometry", {}).get("coordinates", [])
                        if len(coords) >= 2:
                            # Coordinates so [lon, lat]
                            lon, lat = coords[0], coords[1]
                            return (lat, lon)
                _LOGGER.error("Location %s not found in locations data", location)
                return None
    except Exception as e:
        _LOGGER.error("Exception fetching location coords: %s", e)
        return None

async def fetch_daily_uv_forecast(lat: float, lon: float) -> list[dict]:
    """
    Asinhrono pridobi dnevni UV forecast za dano lokacijo.

    Vrne seznam slovarjev, kjer je vsak slovar v obliki:
      {"date": "YYYY-MM-DD", "uv_index": <float>}
    Datum se pretvori v format "YYYY-MM-DD". Podpira formate, kot so "2025-02-11" in "11 Feb 2025".
    """
    url = f"{BASE_UV_URL}?lon={lon}&lat={lat}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching daily UV forecast: HTTP %s", response.status)
                    return []
                text = await response.text()
                soup = BeautifulSoup(text, "html.parser")
                tables = soup.find_all("table")
                if not tables:
                    _LOGGER.error("No tables found in UV forecast page")
                    return []
                forecast = []
                # Iteriramo čez vse tabele in zberemo vse vrstice, kjer sta prvi dve celici veljavni
                for table in tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) < 2:
                            continue
                        date_text = cols[0].get_text(strip=True)
                        uv_str = cols[1].get_text(strip=True)
                        # Poskusimo najprej format "YYYY-MM-DD"
                        try:
                            dt = datetime.strptime(date_text, "%Y-%m-%d")
                        except ValueError:
                            try:
                                # Če ne uspe, poskusimo format "11 Feb 2025"
                                dt = datetime.strptime(date_text, "%d %b %Y")
                            except ValueError:
                                _LOGGER.debug("Skipping row with unparseable date: %s", date_text)
                                continue
                        date_iso = dt.strftime("%Y-%m-%d")
                        try:
                            uv_index = float(uv_str)
                        except ValueError:
                            _LOGGER.debug("Skipping row with invalid UV index: %s", uv_str)
                            continue
                        forecast.append({"date": date_iso, "uv_index": uv_index})
                if not forecast:
                    _LOGGER.error("No valid daily UV forecast entries found")
                    return []
                # Deduplicate po datumu (če je več vnosov za isti dan, ostane prvi)
                seen = set()
                deduped = []
                for item in forecast:
                    if item["date"] not in seen:
                        seen.add(item["date"])
                        deduped.append(item)
                deduped.sort(key=lambda x: x["date"])
                _LOGGER.debug("Collected daily UV forecast entries: %s", deduped)
                return deduped
    except Exception as e:
        _LOGGER.error("Exception fetching daily UV forecast: %s", e)
        return []
