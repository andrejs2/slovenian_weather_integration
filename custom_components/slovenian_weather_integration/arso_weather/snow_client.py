"""Client for fetching snow depth data from ARSO GeoJSON API."""

from __future__ import annotations

import logging
import math

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

SNOW_API_URL = "https://vreme.arso.gov.si/api/1.0/snow_geojson/"


async def fetch_snow_data(session: aiohttp.ClientSession) -> dict:
    """Fetch snow measurement data from ARSO.

    Returns dict keyed by station title (lowercase), each value is a dict:
      - "title": station name
      - "altitude": metres (int or None)
      - "lat", "lon": coordinates
      - "snow_depth_cm": total snow depth in cm (int or None)
      - "snow_new_cm": newly fallen snow in cm (int or None)
      - "updated": ISO timestamp string
    """
    try:
        async with session.get(SNOW_API_URL) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching snow data: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch snow data: {err}") from err

    return _parse_snow_geojson(data)


def _parse_snow_geojson(data: dict) -> dict:
    """Parse GeoJSON snow data into a lookup dict."""
    result: dict[str, dict] = {}
    updated = data.get("tsUpdated")

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        title = props.get("title", "")
        if not title:
            continue

        coords = feature.get("geometry", {}).get("coordinates", [])
        lon = coords[0] if len(coords) > 0 else None
        lat = coords[1] if len(coords) > 1 else None

        altitude = _to_int(props.get("altitude"))

        # Get latest measurement from the most recent day
        snow_depth = None
        snow_new = None
        days = props.get("days", [])
        if days:
            timeline = days[-1].get("timeline", [])
            if timeline:
                latest = timeline[-1]
                snow_depth = _to_int(latest.get("snow"))
                snow_new = _to_int(latest.get("snowNew_val"))

        result[title.lower()] = {
            "title": title,
            "altitude": altitude,
            "lat": lat,
            "lon": lon,
            "snow_depth_cm": snow_depth,
            "snow_new_cm": snow_new,
            "updated": updated,
        }

    return result


def find_nearest_snow_station(
    snow_data: dict,
    lat: float,
    lon: float,
    max_distance_km: float = 15.0,
) -> dict | None:
    """Find the nearest snow measurement station to given coordinates.

    Returns the station dict or None if nothing within max_distance_km.
    """
    best: dict | None = None
    best_dist = float("inf")

    for station in snow_data.values():
        s_lat = station.get("lat")
        s_lon = station.get("lon")
        if s_lat is None or s_lon is None:
            continue

        dist = _haversine_km(lat, lon, s_lat, s_lon)
        if dist < best_dist and dist <= max_distance_km:
            best_dist = dist
            best = {**station, "distance_km": round(dist, 1)}

    return best


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate distance between two points on Earth in km."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _to_int(val: str | int | float | None) -> int | None:
    """Convert a value to int, returning None for empty/invalid."""
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None
