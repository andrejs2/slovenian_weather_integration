"""Client for fetching UTCI (Universal Thermal Climate Index) data from ARSO.

Data source: meteo.arso.gov.si — CSV endpoint per station.
Format: CSV with columns validTime, UTCI (73 hourly entries, ~3 day forecast).
13 stations across Slovenia.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any
from urllib.parse import quote

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

UTCI_BASE_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/sproduct/biomet/table/sl/"
    "UTCI_timeseries_{station}.csv"
)

# All known UTCI stations: display_name -> URL station name
UTCI_STATIONS: dict[str, str] = {
    "Bilje": "BILJE",
    "Bovec": "BOVEC - LETALISCE",
    "Celje": "CELJE - MEDLOG",
    "Črnomelj": "CRNOMELJ - DOBLICE",
    "Kočevje": "KOCEVJE",
    "Kranj": "KRANJ",
    "Maribor": "LETALISCE EDVARDA RUSJANA MARIBOR",
    "Ljubljana": "LJUBLJANA - BEZIGRAD",
    "Murska Sobota": "MURSKA SOBOTA - RAKICAN",
    "Novo mesto": "NOVO MESTO",
    "Portorož": "PORTOROZ - LETALISCE",
    "Rateče": "RATECE",
    "Slovenj Gradec": "SMARTNO PRI SLOVENJ GRADCU",
}

# UTCI stress categories (Slovenian)
UTCI_CATEGORIES: list[tuple[float, str]] = [
    (46, "Izredno močen toplotni stres"),
    (38, "Zelo močen toplotni stres"),
    (32, "Močen toplotni stres"),
    (26, "Zmeren toplotni stres"),
    (9, "Brez toplotnega stresa"),
    (0, "Rahel mrazni stres"),
    (-13, "Zmeren mrazni stres"),
    (-27, "Močen mrazni stres"),
    (-40, "Zelo močen mrazni stres"),
    (float("-inf"), "Izredno močen mrazni stres"),
]


def utci_category(value: float) -> str:
    """Return the UTCI stress category for a given temperature value."""
    for threshold, category in UTCI_CATEGORIES:
        if value > threshold:
            return category
    return UTCI_CATEGORIES[-1][1]


def _parse_utci_csv(text: str) -> list[dict[str, Any]]:
    """Parse UTCI CSV text into a list of dicts.

    CSV format:
        validTime,UTCI
        2026-03-11T00:00:00Z,2.3
        2026-03-11T01:00:00Z,1.8
        ...

    Returns list of {"time": datetime, "utci": float, "category": str}.
    """
    result: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(text))

    for row in reader:
        time_str = row.get("validTime", "").strip()
        utci_str = row.get("UTCI", "").strip()

        if not time_str or not utci_str:
            continue

        try:
            utci_val = float(utci_str)
        except ValueError:
            continue

        try:
            time_val = datetime.fromisoformat(
                time_str.replace("Z", "+00:00")
            )
        except ValueError:
            continue

        result.append({
            "time": time_val.isoformat(),
            "utci": round(utci_val, 1),
            "category": utci_category(utci_val),
        })

    return result


async def fetch_utci_data(
    session: aiohttp.ClientSession,
    selected_stations: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch UTCI data for selected stations.

    Args:
        session: aiohttp client session
        selected_stations: list of display names (keys of UTCI_STATIONS).
            If None or empty, fetches all stations.

    Returns:
        Dict keyed by display name::

            {
                "Ljubljana": {
                    "url_name": "LJUBLJANA - BEZIGRAD",
                    "current": {"time": "...", "utci": 12.3, "category": "..."},
                    "forecast": [{"time": "...", "utci": 14.1, "category": "..."}, ...],
                    "min_utci": 2.1,
                    "max_utci": 18.5,
                },
            }
    """
    stations_to_fetch = selected_stations or list(UTCI_STATIONS.keys())
    result: dict[str, dict[str, Any]] = {}

    for display_name in stations_to_fetch:
        url_name = UTCI_STATIONS.get(display_name)
        if not url_name:
            continue

        encoded = quote(url_name, safe="")
        url = UTCI_BASE_URL.format(station=encoded)

        try:
            async with session.get(url) as response:
                response.raise_for_status()
                text = await response.text()
        except aiohttp.ClientResponseError as err:
            _LOGGER.debug(
                "HTTP %s fetching UTCI for %s: %s",
                err.status, display_name, err.message,
            )
            continue
        except aiohttp.ClientError as err:
            _LOGGER.debug("Failed to fetch UTCI for %s: %s", display_name, err)
            continue

        entries = _parse_utci_csv(text)
        if not entries:
            continue

        # Find current entry (closest to now) — first entry is typically current/most recent
        now = datetime.now().astimezone()
        current = entries[0]
        for entry in entries:
            try:
                entry_time = datetime.fromisoformat(entry["time"])
                if entry_time <= now:
                    current = entry
                else:
                    break
            except (ValueError, TypeError):
                continue

        utci_values = [e["utci"] for e in entries]

        result[display_name] = {
            "url_name": url_name,
            "current": current,
            "forecast": entries,
            "min_utci": min(utci_values),
            "max_utci": max(utci_values),
        }

    return result
