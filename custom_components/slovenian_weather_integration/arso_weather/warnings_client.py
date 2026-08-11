"""Client for fetching weather warnings from ARSO.

Data source: meteo.arso.gov.si — combined CAP XML per region.
5 warning regions, 10 warning types, 4 severity levels.

The combined CAP file (``warning_{region}_latest_CAP.xml``) contains one
``<info>`` block per warning type AND per validity period, covering ~5 days
ahead. The currently valid level for a type is therefore NOT the first block
(nor the ATOM feed title, which does not reflect the currently valid period)
but the block whose onset/expires interval contains the current time.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

CAP_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/warning/text/sl/"
    "warning_{region}_latest_CAP.xml"
)

# Warning regions
WARNING_REGIONS: dict[str, str] = {
    "SLOVENIA_NORTH-WEST": "Severozahodna Slovenija",
    "SLOVENIA_NORTH-EAST": "Severovzhodna Slovenija",
    "SLOVENIA_MIDDLE": "Osrednja Slovenija",
    "SLOVENIA_SOUTH-WEST": "Jugozahodna Slovenija",
    "SLOVENIA_SOUTH-EAST": "Jugovzhodna Slovenija",
}

# Warning types: code -> Slovenian display name
WARNING_TYPES: dict[str, str] = {
    "wind": "Veter",
    "rain": "Dež",
    "TS": "Nevihte",
    "snow": "Sneg",
    "ice": "Poledica/žled",
    "Tx": "Visoka temperatura",
    "Tn": "Nizka temperatura",
    "forestFire": "Požarna ogroženost",
    "avalanche": "Snežni plazovi",
    "coastal": "Obalno opozorilo",
}

# Severity levels
SEVERITY_LEVELS: dict[int, dict[str, str]] = {
    1: {"color": "zelena", "text": "Neznatna ogroženost", "en": "Minor"},
    2: {"color": "rumena", "text": "Zmerna ogroženost", "en": "Moderate"},
    3: {"color": "oranžna", "text": "Velika ogroženost", "en": "Severe"},
    4: {"color": "rdeča", "text": "Zelo velika ogroženost", "en": "Extreme"},
}

# CAP awareness_type parameter ("5; high-temperature") -> warning type code.
# Numeric codes follow MeteoAlarm conventions; the text token is a fallback.
_AWARENESS_TYPE_CODES: dict[str, str] = {
    "1": "wind",
    "2": "snow",
    "3": "TS",
    "5": "Tx",
    "6": "Tn",
    "7": "coastal",
    "8": "forestFire",
    "9": "avalanche",
    "10": "rain",
    "14": "ice",
}
_AWARENESS_TYPE_NAMES: dict[str, str] = {
    "wind": "wind",
    "snow-ice": "snow",
    "thunderstorm": "TS",
    "high-temperature": "Tx",
    "low-temperature": "Tn",
    "coastalevent": "coastal",
    "forest-fire": "forestFire",
    "avalanches": "avalanche",
    "rain": "rain",
    "ice": "ice",
}

_CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"


def region_from_coordinates(lat: float, lon: float) -> str:
    """Map coordinates to the nearest ARSO warning region.

    Uses simple geographic boundaries based on Slovenia's regions.
    """
    # Approximate dividing lines:
    # North/South split around lat 46.05
    # East/West split around lon 14.8
    # Middle region is roughly a band around Ljubljana

    if lat > 46.15:
        # Northern regions
        if lon < 14.8:
            return "SLOVENIA_NORTH-WEST"
        return "SLOVENIA_NORTH-EAST"

    if lat < 45.85:
        # Southern regions
        if lon < 14.6:
            return "SLOVENIA_SOUTH-WEST"
        return "SLOVENIA_SOUTH-EAST"

    # Middle band (45.85 - 46.15)
    if lon < 14.1:
        return "SLOVENIA_SOUTH-WEST"
    if lon > 15.4:
        if lat > 46.0:
            return "SLOVENIA_NORTH-EAST"
        return "SLOVENIA_SOUTH-EAST"

    return "SLOVENIA_MIDDLE"


def _parse_dt(value: str | None) -> datetime | None:
    """Parse a CAP timestamp ("2026-08-11T10:00:00+02:00") to aware datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # ARSO timestamps carry an offset; treat a missing one as UTC.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_info_block(info: ET.Element) -> dict[str, Any] | None:
    """Parse one Slovenian CAP <info> block into a warning period dict."""
    lang = info.findtext(_CAP + "language")
    if lang and not lang.startswith("sl"):
        return None

    warning_type: str | None = None
    level: int | None = None
    for param in info.findall(_CAP + "parameter"):
        name = param.findtext(_CAP + "valueName")
        value = param.findtext(_CAP + "value") or ""
        parts = [p.strip() for p in value.split(";")]
        if name == "awareness_type" and parts:
            warning_type = _AWARENESS_TYPE_CODES.get(parts[0])
            if warning_type is None and len(parts) > 1:
                warning_type = _AWARENESS_TYPE_NAMES.get(parts[1].lower())
        elif name == "awareness_level" and parts:
            try:
                level = int(parts[0])
            except ValueError:
                level = None

    if warning_type is None or level is None:
        _LOGGER.debug(
            "Skipping CAP info block without awareness type/level: %s",
            info.findtext(_CAP + "event"),
        )
        return None

    onset = info.findtext(_CAP + "onset")
    expires = info.findtext(_CAP + "expires")
    return {
        "type": warning_type,
        "type_name": WARNING_TYPES.get(warning_type, warning_type),
        "level": level,
        "level_color": SEVERITY_LEVELS.get(level, {}).get("color", ""),
        "level_text": SEVERITY_LEVELS.get(level, {}).get("text", ""),
        "title": info.findtext(_CAP + "headline"),
        "description": (info.findtext(_CAP + "description") or "").strip(),
        "instruction": (info.findtext(_CAP + "instruction") or "").strip(),
        "onset": onset,
        "expires": expires,
        "onset_dt": _parse_dt(onset),
        "expires_dt": _parse_dt(expires),
        "severity": info.findtext(_CAP + "severity"),
        "urgency": info.findtext(_CAP + "urgency"),
        "certainty": info.findtext(_CAP + "certainty"),
    }


def _is_current(period: dict[str, Any], now: datetime) -> bool:
    """Check whether a warning period is valid at ``now``.

    A missing onset/expires bound is treated as open-ended.
    """
    onset = period["onset_dt"]
    expires = period["expires_dt"]
    if onset is not None and now < onset:
        return False
    if expires is not None and now > expires:
        return False
    return True


def parse_warnings_cap(
    text: str, now: datetime | None = None
) -> dict[str, Any]:
    """Parse a combined CAP XML into current + upcoming warnings.

    Returns ``{"updated": ..., "warnings": [...], "upcoming_warnings": [...]}``
    where ``warnings`` holds the currently valid period per type (level >= 2
    only) and ``upcoming_warnings`` the future periods with level >= 2.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    try:
        root = ET.fromstring(text)
    except ET.ParseError as err:
        raise ArsoApiError(f"Failed to parse warnings CAP XML: {err}") from err

    periods = [
        parsed
        for info in root.findall(_CAP + "info")
        if (parsed := _parse_info_block(info)) is not None
    ]
    if not periods:
        raise ArsoApiError("Warnings CAP XML contains no usable info blocks")

    sent = root.findtext(_CAP + "sent")

    current: dict[str, dict[str, Any]] = {}
    upcoming: list[dict[str, Any]] = []
    for period in periods:
        period["updated"] = sent
        if _is_current(period, now):
            # Keep the most severe period if several overlap "now".
            existing = current.get(period["type"])
            if existing is None or period["level"] > existing["level"]:
                current[period["type"]] = period
        elif (
            period["level"] >= 2
            and period["onset_dt"] is not None
            and period["onset_dt"] > now
        ):
            upcoming.append(period)

    warnings = [w for w in current.values() if w["level"] >= 2]
    warnings.sort(key=lambda w: w["level"], reverse=True)
    upcoming.sort(key=lambda w: w["onset_dt"])

    # Internal datetime helpers must not leak into coordinator data.
    for period in periods:
        period.pop("onset_dt", None)
        period.pop("expires_dt", None)

    return {
        "updated": sent,
        "warnings": warnings,
        "upcoming_warnings": upcoming,
    }


async def fetch_warnings(
    session: aiohttp.ClientSession,
    region: str,
) -> dict[str, Any]:
    """Fetch all weather warnings for a region (single CAP request).

    Args:
        session: aiohttp client session
        region: warning region ID (e.g. "SLOVENIA_MIDDLE")

    Returns::

        {
            "region": "SLOVENIA_MIDDLE",
            "region_name": "Osrednja Slovenija",
            "updated": "2026-08-11T15:25:00+02:00",
            "warnings": [
                {
                    "type": "Tx",
                    "type_name": "Visoka temperatura",
                    "level": 3,
                    "level_color": "oranžna",
                    "level_text": "Velika ogroženost",
                    "title": "Visoka temperatura - velika ogroženost...",
                    "description": "...",
                    "instruction": "...",
                    "onset": "2026-08-11T10:00:00+02:00",
                    "expires": "2026-08-11T19:59:00+02:00",
                    "updated": "...",
                },
            ],
            "upcoming_warnings": [...],  # same shape, future periods
        }
    """
    cap_url = CAP_URL.format(region=region)
    try:
        async with session.get(cap_url) as response:
            response.raise_for_status()
            cap_text = await response.text()
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching warnings CAP: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch warnings: {err}") from err

    result = parse_warnings_cap(cap_text)
    result["region"] = region
    result["region_name"] = WARNING_REGIONS.get(region, region)
    return result
