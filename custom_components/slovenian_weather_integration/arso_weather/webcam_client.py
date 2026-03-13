"""Client for fetching ARSO webcam image URLs.

Uses the dedicated webcam JSON API instead of observationAms,
which provides always-fresh image paths.

Endpoint pattern::

    https://vreme.arso.gov.si/uploads/probase/www/observ/webcam/json/sl/
    webcam_METEO-{station_id}_{direction}_data.json

Each endpoint returns a JSON array of timestamped image entries.
The last entry is the most recent image.
"""

from __future__ import annotations

import logging

import aiohttp

from .station_map import OBSERVATION_STATIONS
from .webcam_stations import WEBCAM_STATIONS

_LOGGER = logging.getLogger(__name__)

WEBCAM_JSON_BASE = (
    "https://vreme.arso.gov.si/uploads/probase/www/observ/webcam"
    "/json/sl//webcam_METEO-{station_id}_{direction}_data.json"
)

WEBCAM_IMAGE_BASE = (
    "https://vreme.arso.gov.si"
)


async def fetch_webcam_urls(
    session: aiohttp.ClientSession,
    locations: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Fetch latest webcam image paths for selected locations.

    Returns::

        {
            "Ljubljana": [
                {"direction": "n", "image_url": "https://...jpg"},
                {"direction": "ne", "image_url": "https://...jpg"},
                ...
            ],
            ...
        }
    """
    result: dict[str, list[dict[str, str]]] = {}

    for loc_name in locations:
        station_id = OBSERVATION_STATIONS.get(loc_name)
        directions = WEBCAM_STATIONS.get(loc_name)
        if not station_id or not directions:
            continue

        cams: list[dict[str, str]] = []
        for direction in directions:
            url = WEBCAM_JSON_BASE.format(
                station_id=station_id, direction=direction
            )
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    if not data:
                        continue
                    # Last entry is the most recent
                    latest = data[-1]
                    path = latest.get("path", "")
                    if path:
                        image_url = f"{WEBCAM_IMAGE_BASE}{path}"
                        cams.append({
                            "direction": direction,
                            "image_url": image_url,
                        })
            except Exception:
                _LOGGER.debug(
                    "Failed to fetch webcam %s/%s",
                    loc_name, direction, exc_info=True,
                )

        if cams:
            result[loc_name] = cams

    return result
