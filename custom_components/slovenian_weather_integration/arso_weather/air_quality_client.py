"""Client for fetching air quality data from ARSO.

Data source: www.arso.gov.si (separate server from meteo.arso.gov.si).
Two XML endpoints:
- Hourly: latest hourly measurements (PM10, PM2.5, O3, NO2, SO2, CO, etc.)
- Daily: daily aggregates (daily averages, max hourly/8-hour values)

23 monitoring stations across Slovenia.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

AQ_HOURLY_URL = (
    "http://www.arso.gov.si/xml/zrak/ones_zrak_urni_podatki_zadnji.xml"
)
AQ_DAILY_URL = (
    "http://www.arso.gov.si/xml/zrak/ones_zrak_dnevni_podatki_zadnji.xml"
)

# All known air quality stations: display_name -> sifra (station code)
# Populated dynamically from XML, but this dict provides the config flow
# selection list with friendly names.
AQ_STATIONS: dict[str, str] = {
    "Celje - bolnica": "E411",
    "Celje - Ljubljanska": "E412",
    "Črna na Koroškem": "E802",
    "Črnomelj - Loka": "E803",
    "Hrastnik": "E414",
    "Ilirska Bistrica": "E804",
    "Iskrba": "E420",
    "Koper": "E423",
    "Kranj": "E417",
    "Krvavec": "E419",
    "Ljubljana - Bežigrad": "E403",
    "Ljubljana - Celovška": "E405",
    "Ljubljana - Vič": "E404",
    "Maribor - Titova": "E407",
    "Maribor - Vrbanski plato": "E408",
    "Murska Sobota - Cankarjeva": "E410",
    "Murska Sobota - Rakičan": "E409",
    "Nova Gorica": "E421",
    "Novo mesto": "E418",
    "Otlica": "E424",
    "Ptuj": "E801",
    "Trbovlje": "E413",
    "Zagorje": "E415",
}

# Reverse lookup: sifra -> display_name
_SIFRA_TO_NAME: dict[str, str] = {v: k for k, v in AQ_STATIONS.items()}

# Hourly measurement fields to extract
_HOURLY_FIELDS = ("pm10", "pm2.5", "so2", "o3", "no2", "co", "benzen", "nox")

# Daily measurement fields to extract
_DAILY_FIELDS = (
    "pm10_dnevna",
    "pm2.5_dnevna",
    "co_max_8urna",
    "so2_dnevna",
    "so2_max_urna",
    "o3_max_urna",
    "o3_max_8urna",
    "no2_max_urna",
)


# European Air Quality Index (EAQI) thresholds
# Each tuple: (upper_bound, level_number, slovenian_label)
# Source: European Environment Agency
# PM2.5/PM10 use 24h average; O3/NO2/SO2 use 1h values
_EAQI_THRESHOLDS: dict[str, list[tuple[float, int, str]]] = {
    "pm2.5": [
        (10, 1, "Dobra"),
        (20, 2, "Zadovoljiva"),
        (25, 3, "Zmerna"),
        (50, 4, "Slaba"),
        (75, 5, "Zelo slaba"),
        (float("inf"), 6, "Izjemno slaba"),
    ],
    "pm10": [
        (20, 1, "Dobra"),
        (40, 2, "Zadovoljiva"),
        (50, 3, "Zmerna"),
        (100, 4, "Slaba"),
        (150, 5, "Zelo slaba"),
        (float("inf"), 6, "Izjemno slaba"),
    ],
    "no2": [
        (40, 1, "Dobra"),
        (90, 2, "Zadovoljiva"),
        (120, 3, "Zmerna"),
        (230, 4, "Slaba"),
        (340, 5, "Zelo slaba"),
        (float("inf"), 6, "Izjemno slaba"),
    ],
    "o3": [
        (50, 1, "Dobra"),
        (100, 2, "Zadovoljiva"),
        (130, 3, "Zmerna"),
        (240, 4, "Slaba"),
        (380, 5, "Zelo slaba"),
        (float("inf"), 6, "Izjemno slaba"),
    ],
    "so2": [
        (100, 1, "Dobra"),
        (200, 2, "Zadovoljiva"),
        (350, 3, "Zmerna"),
        (500, 4, "Slaba"),
        (750, 5, "Zelo slaba"),
        (float("inf"), 6, "Izjemno slaba"),
    ],
}

EAQI_LABELS: dict[int, str] = {
    1: "Dobra",
    2: "Zadovoljiva",
    3: "Zmerna",
    4: "Slaba",
    5: "Zelo slaba",
    6: "Izjemno slaba",
}


def compute_eaqi(station_data: dict[str, Any]) -> dict[str, Any] | None:
    """Compute European Air Quality Index for a station.

    Uses daily averages for PM2.5/PM10 (falls back to hourly),
    and hourly values for O3, NO2, SO2.

    Returns dict with keys: index, label, components (per-pollutant breakdown).
    Returns None if no pollutant data is available.
    """
    hourly = station_data.get("hourly", {})
    daily = station_data.get("daily", {})

    # Gather values: prefer daily average for PM, hourly for gases
    values: dict[str, float] = {}
    for key in ("pm2.5", "pm10"):
        daily_key = f"{key}_dnevna"
        val = daily.get(daily_key) if daily else None
        if val is None:
            val = hourly.get(key)
        if val is not None:
            values[key] = float(val)
    for key in ("o3", "no2", "so2"):
        val = hourly.get(key)
        if val is not None:
            values[key] = float(val)

    if not values:
        return None

    components: dict[str, dict[str, Any]] = {}
    max_level = 0
    for pollutant, concentration in values.items():
        thresholds = _EAQI_THRESHOLDS.get(pollutant, [])
        for upper, level, label in thresholds:
            if concentration <= upper:
                components[pollutant] = {
                    "value": concentration,
                    "index": level,
                    "label": label,
                }
                if level > max_level:
                    max_level = level
                break

    return {
        "index": max_level,
        "label": EAQI_LABELS.get(max_level, "Neznano"),
        "components": components,
    }


def _parse_value(text: str | None) -> float | None:
    """Parse a numeric value from XML text.

    Handles empty strings, None, and '<1' (below detection limit → 0.5).
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    if text.startswith("<"):
        # e.g. "<1" means below detection limit
        try:
            return float(text[1:]) / 2
        except (ValueError, IndexError):
            return None
    try:
        return float(text)
    except ValueError:
        return None


async def _fetch_xml(
    session: aiohttp.ClientSession, url: str
) -> ET.Element:
    """Fetch and parse an XML document from ARSO."""
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            text = await response.text()
            _LOGGER.debug(
                "AQ XML fetch %s: status=%s, length=%d, first200=%s",
                url.split("/")[-1],
                response.status,
                len(text),
                text[:200].replace("\n", " "),
            )
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching air quality: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch air quality: {err}") from err

    try:
        root = ET.fromstring(text)
        _LOGGER.debug(
            "AQ XML parsed: root_tag=%s, child_tags=%s, postaja_count=%d",
            root.tag,
            [c.tag for c in root][:5],
            len(list(root.iter("postaja"))),
        )
        return root
    except ET.ParseError as err:
        raise ArsoApiError(f"Failed to parse air quality XML: {err}") from err


def _parse_hourly_xml(
    root: ET.Element,
    selected_codes: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Parse hourly air quality XML into a dict keyed by station code."""
    result: dict[str, dict[str, Any]] = {}

    # Diagnostic: log actual sifra values from XML
    all_sifras = []
    for p in root.iter("postaja"):
        s = p.get("sifra", "")
        mm = (p.findtext("merilno_mesto") or "").strip()
        all_sifras.append(f"{s}({mm})")
    _LOGGER.debug(
        "AQ XML sifra values: %s (filtering by: %s)",
        all_sifras[:10],
        selected_codes,
    )

    for postaja in root.iter("postaja"):
        sifra = postaja.get("sifra", "").strip()
        if not sifra:
            continue
        if selected_codes and sifra not in selected_codes:
            continue

        station: dict[str, Any] = {
            "name": _SIFRA_TO_NAME.get(
                sifra,
                (postaja.findtext("merilno_mesto") or sifra).strip(),
            ),
            "sifra": sifra,
            "lat": _parse_value(postaja.get("wgs84_sirina")),
            "lon": _parse_value(postaja.get("wgs84_dolzina")),
            "altitude": _parse_value(postaja.get("nadm_visina")),
            "datum_od": (postaja.findtext("datum_od") or "").strip() or None,
            "datum_do": (postaja.findtext("datum_do") or "").strip() or None,
        }

        for field in _HOURLY_FIELDS:
            # pm2.5 has a dot in the tag name
            station[field] = _parse_value(postaja.findtext(field))

        result[sifra] = station

    return result


def _parse_daily_xml(
    root: ET.Element,
    selected_codes: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Parse daily air quality XML into a dict keyed by station code."""
    result: dict[str, dict[str, Any]] = {}

    for postaja in root.iter("postaja"):
        sifra = postaja.get("sifra", "").strip()
        if not sifra:
            continue
        if selected_codes and sifra not in selected_codes:
            continue

        station: dict[str, Any] = {
            "datum": (postaja.findtext("datum") or "").strip() or None,
        }

        for field in _DAILY_FIELDS:
            station[field] = _parse_value(postaja.findtext(field))

        result[sifra] = station

    return result


async def fetch_air_quality_data(
    session: aiohttp.ClientSession,
    selected_stations: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch air quality data for selected stations.

    Args:
        session: aiohttp client session
        selected_stations: list of display names (keys of AQ_STATIONS).
            If None or empty, fetches all stations.

    Returns:
        Dict keyed by display name::

            {
                "Ljubljana - Bežigrad": {
                    "sifra": "E22",
                    "lat": 46.065, "lon": 14.512, "altitude": 299,
                    "hourly": {
                        "pm10": 23.0, "pm2.5": 12.0, "o3": 45.0,
                        "no2": 18.0, "so2": 3.0, "co": 0.4,
                        "datum_od": "...", "datum_do": "...",
                    },
                    "daily": {
                        "pm10_dnevna": 25.0, "o3_max_8urna": 67.0,
                        "datum": "...",
                    },
                },
            }
    """
    # Resolve display names to station codes
    selected_codes: set[str] | None = None
    if selected_stations:
        selected_codes = {
            AQ_STATIONS[name]
            for name in selected_stations
            if name in AQ_STATIONS
        }
    _LOGGER.debug(
        "AQ fetch: selected_stations=%s, selected_codes=%s",
        selected_stations,
        selected_codes,
    )

    # Fetch both endpoints
    hourly_root = await _fetch_xml(session, AQ_HOURLY_URL)
    daily_root = await _fetch_xml(session, AQ_DAILY_URL)

    hourly_data = _parse_hourly_xml(hourly_root, selected_codes)
    daily_data = _parse_daily_xml(daily_root, selected_codes)
    _LOGGER.debug(
        "AQ parsed: hourly_stations=%s, daily_stations=%s",
        list(hourly_data.keys()),
        list(daily_data.keys()),
    )

    # Also discover stations not in our hardcoded list
    for postaja in hourly_root.iter("postaja"):
        sifra = postaja.get("sifra", "").strip()
        name = (postaja.findtext("merilno_mesto") or "").strip()
        if sifra and name and sifra not in _SIFRA_TO_NAME:
            _LOGGER.debug(
                "Discovered new AQ station: %s (%s)", name, sifra
            )

    # Merge hourly + daily into final result keyed by display name
    result: dict[str, dict[str, Any]] = {}
    for sifra, hourly in hourly_data.items():
        display_name = hourly.pop("name", sifra)
        station_info: dict[str, Any] = {
            "sifra": sifra,
            "lat": hourly.pop("lat", None),
            "lon": hourly.pop("lon", None),
            "altitude": hourly.pop("altitude", None),
            "hourly": hourly,
        }
        daily = daily_data.get(sifra, {})
        if daily:
            station_info["daily"] = daily
        result[display_name] = station_info

    return result
