"""Client for fetching bio-weather forecast from ARSO."""

from __future__ import annotations

import logging

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

BIO_WEATHER_URL = (
    "https://vreme.arso.gov.si/uploads/probase/www/fproduct/json/sl/"
    "fcast_bio_si_d1_text.json"
)


async def fetch_bio_weather(session: aiohttp.ClientSession) -> dict:
    """Fetch and parse bio-weather forecast from ARSO.

    Returns dict with keys: bio_weather, uv_index, pollen, updated.
    Values are text strings.
    """
    try:
        async with session.get(BIO_WEATHER_URL) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching bio-weather: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch bio-weather: {err}") from err

    return _parse_bio_weather(data)


def _parse_bio_weather(data: dict) -> dict:
    """Parse bio-weather JSON into structured data."""
    sections = data.get("section", [])
    result: dict[str, str | None] = {
        "bio_weather": None,
        "uv_index": None,
        "pollen": None,
        "updated": data.get("tsUpdated"),
    }

    for section in sections:
        title = (section.get("title") or "").upper()
        para = section.get("para", "")
        if isinstance(para, list):
            para = "\n".join(str(p) for p in para)

        if "BIOVREME" in title:
            result["bio_weather"] = para
        elif "UV" in title:
            result["uv_index"] = para
        elif "CVET" in title or "PRAH" in title:
            result["pollen"] = para

    return result
