"""ARSO Agrometeo (agricultural meteorology) data client.

Fetches daily observation and forecast data for agrometeo stations from
the ARSO GeoJSON endpoints. Each station provides soil temperature,
evapotranspiration, water balance, and standard weather parameters.
"""

from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientSession

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

AGRO_OBS_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/"
    "observationKlima_si-agro.json"
)
AGRO_FORECAST_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/"
    "forecastKlima_si-agro.json"
)

# Known agrometeo stations (title -> region parentId).
# Reference stations per region + sub-stations from ARSO metadata.
AGRO_STATIONS: dict[str, str] = {
    "Bilje pri Novi Gorici": "SI_GORISKA_",
    "Bovec": "SI_BOVSKA_",
    "Breginj": "SI_BOVSKA_",
    "Celje": "SI_SAVINJSKA_",
    "Črnomelj": "SI_BELOKRANJSKA_",
    "Gačnik": "SI_PODRAVSKA_",
    "Godnje": "SI_GORISKA_",
    "Idrija": "SI_BOVSKA_",
    "Ilirska Bistrica": "SI_NOTRANJSKO-KRASKA_",
    "Kočevje": "SI_KOCEVSKA_",
    "Koper": "SI_OBALNO-KRASKA_",
    "Lendava": "SI_POMURSKA_",
    "Letališče Cerklje ob Krki": "SI_SPODNJEPOSAVSKA_",
    "Letališče Edvarda Rusjana Maribor": "SI_PODRAVSKA_",
    "Letališče Jožeta Pučnika Ljubljana": "SI_GORENJSKA_",
    "Letališče Lesce": "SI_GORENJSKA_",
    "Letališče Portorož": "SI_OBALNO-KRASKA_",
    "Ljubljana": "SI_OSREDNJESLOVENSKA_",
    "Malkovec": "SI_SPODNJEPOSAVSKA_",
    "Maribor": "SI_PODRAVSKA_",
    "Metlika": "SI_BELOKRANJSKA_",
    "Murska Sobota": "SI_POMURSKA_",
    "Novo mesto": "SI_DOLENJSKA_",
    "Podčetrtek": "SI_SAVINJSKA_",
    "Podnanos": "SI_GORISKA_",
    "Postojna": "SI_NOTRANJSKO-KRASKA_",
    "Rateče": "SI_ZGORNJESAVSKA_",
    "Ravne na Koroškem": "SI_KOROSKA_",
    "Rogaška Slatina": "SI_SAVINJSKA_",
    "Šebreljski vrh": "SI_BOVSKA_",
    "Šmartno pri Slovenj Gradcu": "SI_KOROSKA_",
    "Tolmin - Volče": "SI_BOVSKA_",
    "Trebnje": "SI_DOLENJSKA_",
    "Velike Lašče": "SI_KOCEVSKA_",
    "Vrhnika": "SI_OSREDNJESLOVENSKA_",
    "Zgornja Kapla": "SI_KOROSKA_",
}


def _safe_float(val: Any) -> float | None:
    """Parse a float value, returning None for empty/invalid."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    """Parse an int value, returning None for empty/invalid."""
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _parse_obs_entry(entry: dict) -> dict[str, Any]:
    """Parse an observation timeline entry into clean dict."""
    return {
        "tklim": _safe_float(entry.get("tklim")),
        "tn": _safe_float(entry.get("tn")),
        "tx": _safe_float(entry.get("tx")),
        "tn_5_cm": _safe_float(entry.get("tn_5_cm")),
        "tg_5_cm": _safe_float(entry.get("tg_5_cm")),
        "tg_10_cm": _safe_float(entry.get("tg_10_cm")),
        "tg_30_cm": _safe_float(entry.get("tg_30_cm")),
        "tp_24h_acc": _safe_float(entry.get("tp_24h_acc")),
        "sunDur": _safe_float(entry.get("sunDur")),
        "etp": _safe_float(entry.get("etp")),
        "wBal": _safe_float(entry.get("wBal")),
        "ffavg_val": _safe_int(entry.get("ffavg_val")),
        "ffmax_val": _safe_int(entry.get("ffmax_val")),
        "thi": _safe_float(entry.get("thi")),
    }


def _parse_forecast_entry(entry: dict) -> dict[str, Any]:
    """Parse a forecast timeline entry into clean dict."""
    result = _parse_obs_entry(entry)
    result["rhavg"] = _safe_float(entry.get("rhavg"))
    result["wwsyn_icon"] = entry.get("wwsyn_icon", "")
    result["clouds_icon"] = entry.get("clouds_icon_wwsyn_icon", "")
    # Forecast may use tnsyn/txsyn instead of tn/tx
    if result["tn"] is None:
        result["tn"] = _safe_float(entry.get("tnsyn"))
    if result["tx"] is None:
        result["tx"] = _safe_float(entry.get("txsyn"))
    return result


def _parse_station_features(
    geojson: dict,
    parser: callable,
    selected: list[str] | None,
) -> dict[str, dict[str, Any]]:
    """Parse GeoJSON features into station data dicts."""
    result: dict[str, dict[str, Any]] = {}
    for feature in geojson.get("features", []):
        props = feature.get("properties", {})
        title = props.get("title", "")
        if not title:
            continue
        if selected and title not in selected:
            continue

        days = props.get("days", [])
        parsed_days: list[dict[str, Any]] = []
        for day in days:
            timeline = day.get("timeline", [])
            if not timeline:
                continue
            entry = parser(timeline[0])
            entry["date"] = day.get("date", "")
            entry["sunrise"] = day.get("sunrise", "")
            entry["sunset"] = day.get("sunset", "")
            parsed_days.append(entry)

        coords = feature.get("geometry", {}).get("coordinates", [])
        result[title] = {
            "lat": coords[1] if len(coords) > 1 else None,
            "lon": coords[0] if coords else None,
            "region_id": props.get("parentId", ""),
            "station_id": props.get("id", ""),
            "days": parsed_days,
        }
    return result


async def fetch_agrometeo_data(
    session: ClientSession,
    selected_stations: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch observation + forecast data for agrometeo stations.

    Returns dict keyed by station title::

        {
            "Ljubljana": {
                "current": {...},       # latest observation day
                "history": [...],       # previous observation days
                "forecast": [...],      # forecast days
                "lat": float,
                "lon": float,
                "updated": str,
            },
        }
    """
    # Fetch observations
    try:
        async with session.get(AGRO_OBS_URL) as resp:
            resp.raise_for_status()
            obs_json = await resp.json(content_type=None)
    except Exception as err:
        raise ArsoApiError(
            f"Failed to fetch agrometeo observations: {err}"
        ) from err

    obs_data = _parse_station_features(obs_json, _parse_obs_entry, selected_stations)

    # Build result from observations
    result: dict[str, dict[str, Any]] = {}
    updated = obs_json.get("tsUpdated", "")

    for title, sdata in obs_data.items():
        days = sdata.pop("days", [])
        station: dict[str, Any] = {
            "lat": sdata["lat"],
            "lon": sdata["lon"],
            "region_id": sdata["region_id"],
            "station_id": sdata["station_id"],
            "updated": updated,
        }
        if days:
            station["current"] = days[-1]
            station["history"] = days[:-1]
        else:
            station["current"] = {}
            station["history"] = []
        station["forecast"] = []
        result[title] = station

    # Fetch forecast and merge
    try:
        async with session.get(AGRO_FORECAST_URL) as resp:
            resp.raise_for_status()
            fc_json = await resp.json(content_type=None)
        fc_data = _parse_station_features(
            fc_json, _parse_forecast_entry, selected_stations
        )
        for title, sdata in fc_data.items():
            if title in result:
                result[title]["forecast"] = sdata.get("days", [])
    except Exception:
        _LOGGER.warning("Failed to fetch agrometeo forecast", exc_info=True)

    return result
