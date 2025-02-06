"""
uv_index.py

Ta modul vsebuje asinkrono funkcijo za pridobitev UV indeksa za dano lokacijo.
Pridobiva se najprej latitude in longitude iz URL-ja LOCATIONS_URL,
potem se pokliče stran Temis, ki vrne UV indeks in dnevni UV forecast.
"""

import aiohttp
import logging
from bs4 import BeautifulSoup
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# URL za pridobitev UV indeksa (Temis)
BASE_UV_URL = "https://www.temis.nl/uvradiation/nrt/uvindex.php"

async def fetch_uv_index(lat: float, lon: float) -> float | None:
    """Asinhrono pridobi trenutni UV indeks za dano lat in lon."""
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
                # Vrne samo prvo veljavno številko, kot trenutni UV indeks
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
    Datum se pretvori v format "YYYY-MM-DD", če je v izvorni HTML strani v drugem formatu.
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
                # Predpostavljamo, da prava tabela vsebuje več vrstic z datumom in UV indeksom.
                for table in tables:
                    rows = table.find_all("tr")
                    for row in rows:
                        cols = row.find_all("td")
                        if len(cols) >= 2:
                            date_text = cols[0].get_text(strip=True)
                            uv_str = cols[1].get_text(strip=True)
                            try:
                                # Najprej poskusimo, če je date_text v formatu "YYYY-MM-DD"
                                dt = datetime.strptime(date_text, "%Y-%m-%d")
                            except ValueError:
                                try:
                                    # Če ni, poskusimo "DD-MM-YYYY"
                                    dt = datetime.strptime(date_text, "%d-%m-%Y")
                                except ValueError:
                                    _LOGGER.warning("Could not parse date: %s", date_text)
                                    continue
                            date_iso = dt.strftime("%Y-%m-%d")
                            try:
                                uv_index = float(uv_str)
                            except ValueError:
                                _LOGGER.warning("Invalid UV index value: %s", uv_str)
                                continue
                            forecast.append({"date": date_iso, "uv_index": uv_index})
                    if forecast:
                        break  # Uporabimo prvo tabelo, ki vsebuje veljavne vnose
                if not forecast:
                    _LOGGER.error("No valid daily UV forecast entries found")
                return forecast
    except Exception as e:
        _LOGGER.error("Exception fetching daily UV forecast: %s", e)
        return []
