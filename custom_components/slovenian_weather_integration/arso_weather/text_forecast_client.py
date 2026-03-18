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

# Audio forecast — MP3 recorded by ARSO prognostik, updated daily.
# Can be played via media_player.play_media service in HA.
AUDIO_FORECAST_URL = (
    "https://www.vreme.si/uploads/probase/www/fproduct/media/sl/"
    "fcast_si_audio_mbr.mp3"
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
    """Parse text forecast JSON into structured data.

    Builds a full composed forecast from individual sections, matching the
    structure shown on vreme.arso.gov.si and the audio forecast MP3.

    Returns dict with keys: forecast (full text), summary, outlook,
    weather_image, updated, audio_url.
    """
    sections = data.get("section", [])
    result: dict[str, str | None] = {
        "forecast": None,
        "summary": None,
        "outlook": None,
        "weather_image": None,
        "updated": data.get("tsUpdated"),
        "audio_url": AUDIO_FORECAST_URL,
    }

    # Collect paragraphs per named group
    forecast_si: list[str] = []
    forecast_neighbors: list[str] = []
    outlook: list[str] = []
    warning: list[str] = []
    weather_image: list[str] = []
    current_group: str | None = None

    for section in sections:
        title = (section.get("title") or "").strip()
        title_upper = title.upper()
        para = section.get("para", "")
        if isinstance(para, list):
            para = "\n".join(str(p) for p in para)
        if not para:
            current_group = None
            continue

        # "POVZETEK" must be checked before "NAPOVED ZA SLOVENIJO"
        # because the summary title contains both strings.
        if "POVZETEK" in title_upper:
            result["summary"] = para
            current_group = None
        elif "NAPOVED ZA SLOVENIJO" in title_upper:
            forecast_si.append(para)
            current_group = "si"
        elif "SOSEDNJE POKRAJINE" in title_upper:
            forecast_neighbors.append(para)
            current_group = "neighbors"
        elif "OBETI" in title_upper:
            outlook.append(para)
            current_group = "outlook"
        elif "OPOZORILO" in title_upper:
            warning.append(para)
            current_group = "warning"
        elif "VREMENSKA SLIKA" in title_upper:
            weather_image.append(para)
            current_group = "weather_image"
        elif not title:
            # Continuation paragraph (untitled) belongs to current group
            if current_group == "si":
                forecast_si.append(para)
            elif current_group == "neighbors":
                forecast_neighbors.append(para)
            elif current_group == "outlook":
                outlook.append(para)
            elif current_group == "warning":
                warning.append(para)
            elif current_group == "weather_image":
                weather_image.append(para)

    # forecast = only "Napoved za Slovenijo" (today + tomorrow paragraphs)
    result["forecast"] = "\n\n".join(forecast_si) if forecast_si else None
    result["outlook"] = "\n\n".join(outlook) if outlook else None
    result["weather_image"] = (
        "\n\n".join(weather_image) if weather_image else None
    )

    return result
