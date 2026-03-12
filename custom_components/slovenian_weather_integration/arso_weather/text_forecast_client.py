"""Client for fetching text weather forecast from ARSO."""

from __future__ import annotations

import logging

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

TEXT_FORECAST_URL = (
    "https://vreme.arso.gov.si/uploads/probase/www/fproduct/json/sl/"
    "fcast_si_text.json"
)


async def fetch_text_forecast(session: aiohttp.ClientSession) -> dict:
    """Fetch and parse text forecast from ARSO.

    Returns dict with keys: forecast, outlook, weather_image, updated.
    Values are text strings suitable for TTS.
    """
    try:
        async with session.get(TEXT_FORECAST_URL) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching text forecast: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch text forecast: {err}") from err

    return _parse_text_forecast(data)


def _parse_text_forecast(data: dict) -> dict:
    """Parse text forecast JSON into structured data."""
    sections = data.get("section", [])
    result: dict[str, str | None] = {
        "forecast": None,
        "outlook": None,
        "weather_image": None,
        "updated": data.get("tsUpdated"),
    }

    for section in sections:
        title = (section.get("title") or "").upper()
        para = section.get("para", "")
        if isinstance(para, list):
            para = "\n".join(str(p) for p in para)

        if "NAPOVED ZA SLOVENIJO" in title:
            result["forecast"] = para
        elif "OBETI" in title:
            result["outlook"] = para
        elif "VREMENSKA SLIKA" in title:
            result["weather_image"] = para

    return result
