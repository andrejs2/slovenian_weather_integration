"""Client for fetching avalanche bulletin data (EAWS / CAAMLv6).

Supports three bulletin sources:
- SI (Slovenia) — from lawinen-warnung.eu
- AT-06 (Štajerska / Steiermark) — from lawinen-warnung.eu (Slovenian version)
- AT-02 (Koroška / Kärnten) — from avalanche.report (German, no Slovenian)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

# Bulletin sources: key -> URL template
# {date} placeholder is replaced with YYYY-MM-DD
BULLETIN_URLS: dict[str, str] = {
    "SI": (
        "https://static.lawinen-warnung.eu/bulletins/{date}/"
        "{date}_SI_sl_SI_CAAMLv6.json"
    ),
    "AT-06": (
        "https://static.lawinen-warnung.eu/bulletins/{date}/"
        "{date}_AT-06_sl_SI_CAAMLv6.json"
    ),
    "AT-02": (
        "https://static.avalanche.report/bulletins/{date}/"
        "{date}_AT-02_de_CAAMLv6.json"
    ),
}

# All known avalanche bulletin regions: display_name -> regionID
# Grouped by source for clarity.
AVALANCHE_REGIONS: dict[str, str] = {
    # --- Slovenija (SI) ---
    "Zahodne Karavanke": "SI-1",
    "Osrednje Karavanke": "SI-2",
    "Kamniške Alpe": "SI-3",
    "Savinjske Alpe in Koroška": "SI-4",
    "Zahodne Julijske Alpe": "SI-6",
    "Osrednje Julijske Alpe": "SI-7",
    "Vzhodne Julijske Alpe": "SI-8",
    "Južno predgorje Julijskih Alp": "SI-9",
    "Južne Julijske Alpe": "SI-10",
    "Vzhodno predgorje Julijskih Alp": "SI-11",
    "Javorniki in Snežnik": "SI-16",
    # --- Koroška / Kärnten (AT-02) — border regions ---
    "Karavanke zahod (AT)": "AT-02-17",
    "Karavanke sredina (AT)": "AT-02-18",
    "Karavanke vzhod (AT)": "AT-02-19",
    "Karnijske Alpe Lesachtal (AT)": "AT-02-14",
    "Karnijske Alpe Plöckenpass (AT)": "AT-02-15-01",
    "Karnijske Alpe Nassfeld (AT)": "AT-02-15-02",
    "Karnijske Alpe Oisternig (AT)": "AT-02-16",
    "Ziljske Alpe zahod (AT)": "AT-02-10",
    "Ziljske Alpe sredina (AT)": "AT-02-11",
    "Ziljske Alpe vzhod (AT)": "AT-02-12-01",
    "Beljaške Alpe (AT)": "AT-02-13",
    "Kreuzeckgruppe (AT)": "AT-02-09",
    # --- Štajerska / Steiermark (AT-06) — border regions ---
    "Vzhodna Koralpa (AT)": "AT-06-16",
    "Murške gore, Krške Alpe (AT)": "AT-06-18",
    "Seetalske Alpe (AT)": "AT-06-17",
    "Stub in Gleinalpe (AT)": "AT-06-15",
    "Južni Schladmingški Tauern (AT)": "AT-06-04-02",
    "Južni Wölzer Tauern (AT)": "AT-06-07",
}

# Reverse lookup: regionID -> display_name
_REGION_ID_TO_NAME: dict[str, str] = {v: k for k, v in AVALANCHE_REGIONS.items()}

# EAWS danger level string -> numeric (1-5)
DANGER_LEVELS: dict[str, int] = {
    "low": 1,
    "moderate": 2,
    "considerable": 3,
    "high": 4,
    "very_high": 5,
}

# Slovenian labels for danger levels
DANGER_LABELS: dict[int, str] = {
    1: "Majhna",
    2: "Zmerna",
    3: "Znatna",
    4: "Velika",
    5: "Zelo velika",
}

# Slovenian labels for avalanche problem types
PROBLEM_TYPE_LABELS: dict[str, str] = {
    "new_snow": "Nov sneg",
    "wind_slab": "Klože",
    "persistent_weak_layers": "Starejše šibke plasti",
    "wet_snow": "Moker sneg",
    "gliding_snow": "Plazenje snega",
    "cornices": "Opasti",
    "no_distinct_avalanche_problem": "Brez izrazitega problema",
}


def _source_for_region(region_id: str) -> str:
    """Determine bulletin source key from region ID prefix."""
    if region_id.startswith("AT-02"):
        return "AT-02"
    if region_id.startswith("AT-06"):
        return "AT-06"
    return "SI"


def _parse_danger_ratings(ratings: list[dict]) -> dict[str, Any]:
    """Parse dangerRatings into structured dict with elevation split."""
    danger_high = 0
    danger_low = 0
    elevation = None

    for rating in ratings:
        level = DANGER_LEVELS.get(rating.get("mainValue", ""), 0)
        elev = rating.get("elevation", {})
        if "lowerBound" in elev:
            danger_high = level
            bound = elev["lowerBound"]
            elevation = int(bound) if str(bound).isdigit() else str(bound)
        elif "upperBound" in elev:
            danger_low = level
            bound = elev["upperBound"]
            elevation = int(bound) if str(bound).isdigit() else str(bound)
        else:
            danger_high = level
            danger_low = level

    max_danger = max(danger_high, danger_low)
    return {
        "danger_rating_high": danger_high,
        "danger_rating_low": danger_low,
        "danger_label_high": DANGER_LABELS.get(danger_high, "—"),
        "danger_label_low": DANGER_LABELS.get(danger_low, "—"),
        "elevation_boundary": elevation,
        "max_danger_rating": max_danger,
        "max_danger_label": DANGER_LABELS.get(max_danger, "—"),
    }


def _parse_problems(problems: list[dict]) -> list[dict[str, Any]]:
    """Parse avalancheProblems into structured list."""
    result = []
    for prob in problems:
        ptype = prob.get("problemType", "")
        elev = prob.get("elevation", {})
        result.append({
            "type": ptype,
            "type_label": PROBLEM_TYPE_LABELS.get(ptype, ptype),
            "aspects": prob.get("aspects", []),
            "elevation_lower_bound": elev.get("lowerBound"),
            "elevation_upper_bound": elev.get("upperBound"),
            "valid_time_period": prob.get("validTimePeriod", "all_day"),
        })
    return result


def _parse_bulletins(
    raw_data: dict,
    selected_ids: set[str] | None,
) -> dict[str, dict[str, Any]]:
    """Parse CAAMLv6 bulletin JSON into result dict keyed by display name."""
    bulletins = raw_data.get("bulletins", [])
    result: dict[str, dict[str, Any]] = {}

    for bulletin in bulletins:
        danger = _parse_danger_ratings(bulletin.get("dangerRatings", []))
        problems = _parse_problems(bulletin.get("avalancheProblems", []))

        activity = bulletin.get("avalancheActivity", {})
        snowpack = bulletin.get("snowpackStructure", {})
        weather = bulletin.get("weatherForecast", {})
        tendency_list = bulletin.get("tendency", [])
        tendency_text = (
            tendency_list[0].get("highlights", "") if tendency_list else ""
        )
        tendency_type = (
            tendency_list[0].get("tendencyType", "") if tendency_list else ""
        )

        valid_time = bulletin.get("validTime", {})

        shared_data = {
            **danger,
            "problems": problems,
            "highlights": activity.get("highlights", ""),
            "activity_comment": activity.get("comment", ""),
            "snowpack_comment": snowpack.get("comment", ""),
            "weather_comment": weather.get("comment", ""),
            "tendency": tendency_text,
            "tendency_type": tendency_type,
            "publication_time": bulletin.get("publicationTime", ""),
            "valid_start": valid_time.get("startTime", ""),
            "valid_end": valid_time.get("endTime", ""),
        }

        for region in bulletin.get("regions", []):
            region_id = region.get("regionID", "")

            if selected_ids and region_id not in selected_ids:
                continue

            # Use our display name if known, otherwise API-provided name
            region_name = _REGION_ID_TO_NAME.get(
                region_id, region.get("name", region_id)
            )

            result[region_name] = {
                "region_id": region_id,
                **shared_data,
            }

    return result


async def _fetch_source(
    session: aiohttp.ClientSession,
    source_key: str,
    dates_to_try: list[str],
) -> dict | None:
    """Fetch bulletin from a single source, trying today then yesterday."""
    url_template = BULLETIN_URLS[source_key]

    for date_str in dates_to_try:
        url = url_template.format(date=date_str)
        try:
            async with session.get(url) as response:
                if response.status == 404:
                    _LOGGER.debug(
                        "No %s bulletin for %s, trying previous day",
                        source_key, date_str,
                    )
                    continue
                response.raise_for_status()
                data = await response.json(content_type=None)
                _LOGGER.debug(
                    "Fetched %s avalanche bulletin for %s",
                    source_key, date_str,
                )
                return data
        except aiohttp.ClientResponseError as err:
            if err.status == 404:
                continue
            raise ArsoApiError(
                f"HTTP {err.status} fetching {source_key} avalanche data: "
                f"{err.message}"
            ) from err
        except aiohttp.ClientError as err:
            raise ArsoApiError(
                f"Request failed for {source_key} avalanche data: {err}"
            ) from err

    return None


async def fetch_avalanche_data(
    session: aiohttp.ClientSession,
    selected_regions: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch and parse avalanche bulletin data from all needed sources.

    Returns dict keyed by region display name with danger ratings,
    avalanche problems, and text forecasts.
    Tries today's bulletin first, falls back to yesterday if not found.
    """
    # Build selected IDs and determine which sources to fetch
    selected_ids: set[str] | None = None
    needed_sources: set[str] = {"SI"}  # always fetch SI

    if selected_regions:
        selected_ids = set()
        needed_sources = set()
        for name in selected_regions:
            region_id = AVALANCHE_REGIONS.get(name)
            if region_id:
                selected_ids.add(region_id)
                needed_sources.add(_source_for_region(region_id))

    now = datetime.now(tz=timezone.utc)
    dates_to_try = [
        now.strftime("%Y-%m-%d"),
        (now - timedelta(days=1)).strftime("%Y-%m-%d"),
    ]

    result: dict[str, dict[str, Any]] = {}

    for source_key in needed_sources:
        raw_data = await _fetch_source(session, source_key, dates_to_try)
        if raw_data is None:
            _LOGGER.warning("No avalanche bulletin available for %s", source_key)
            continue
        source_result = _parse_bulletins(raw_data, selected_ids)
        result.update(source_result)

    if not result:
        raise ArsoApiError("No avalanche bulletin available")

    return result
