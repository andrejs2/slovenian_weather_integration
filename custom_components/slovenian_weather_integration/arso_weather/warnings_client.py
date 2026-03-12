"""Client for fetching weather warnings from ARSO.

Data source: meteo.arso.gov.si — ATOM feed + CAP XML per warning type.
5 warning regions, 10 warning types, 4 severity levels.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

ATOM_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/warning/text/sl/"
    "warning_{region}_latest.atom"
)
CAP_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/warning/text/sl/"
    "warning_{type}_{region}_latest_CAP.xml"
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

# XML namespaces
_NS_ATOM = {"atom": "http://www.w3.org/2005/Atom"}
_NS_CAP = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


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


def _parse_level_from_title(title: str) -> int:
    """Extract warning level (1-4) from ATOM entry title.

    Title format: "Veter - neznatna ogroženost (Stopnja 1/4) - Slovenija / osrednja"
    """
    match = re.search(r"Stopnja\s+(\d)/4", title)
    if match:
        return int(match.group(1))
    return 1


def _parse_type_from_url(url: str) -> str | None:
    """Extract warning type code from CAP URL.

    URL: .../warning_wind_SLOVENIA_MIDDLE_latest_CAP.xml
    """
    match = re.search(r"warning_(\w+)_SLOVENIA", url)
    if match:
        return match.group(1)
    return None


def _parse_atom_feed(text: str) -> list[dict[str, Any]]:
    """Parse ATOM feed into a list of warning summaries."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as err:
        raise ArsoApiError(f"Failed to parse warnings ATOM: {err}") from err

    warnings: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", _NS_ATOM):
        title_el = entry.find("atom:title", _NS_ATOM)
        link_el = entry.find("atom:link", _NS_ATOM)
        updated_el = entry.find("atom:updated", _NS_ATOM)

        title = title_el.text if title_el is not None else ""
        url = link_el.get("href", "") if link_el is not None else ""
        updated = updated_el.text if updated_el is not None else None

        warning_type = _parse_type_from_url(url)
        level = _parse_level_from_title(title)

        if warning_type:
            warnings.append({
                "type": warning_type,
                "type_name": WARNING_TYPES.get(warning_type, warning_type),
                "level": level,
                "level_color": SEVERITY_LEVELS.get(level, {}).get("color", ""),
                "level_text": SEVERITY_LEVELS.get(level, {}).get("text", ""),
                "title": title,
                "cap_url": url,
                "updated": updated,
            })

    return warnings


def _parse_cap_xml(text: str) -> dict[str, Any]:
    """Parse CAP XML for detailed warning info (Slovenian language)."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as err:
        raise ArsoApiError(f"Failed to parse CAP XML: {err}") from err

    result: dict[str, Any] = {
        "sent": root.findtext("{urn:oasis:names:tc:emergency:cap:1.2}sent"),
    }

    # Find Slovenian info block
    for info in root.findall("{urn:oasis:names:tc:emergency:cap:1.2}info"):
        lang = info.findtext("{urn:oasis:names:tc:emergency:cap:1.2}language")
        if lang and lang != "sl":
            continue

        result["event"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}event"
        )
        result["headline"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}headline"
        )
        result["description"] = (
            info.findtext(
                "{urn:oasis:names:tc:emergency:cap:1.2}description"
            )
            or ""
        ).strip()
        result["instruction"] = (
            info.findtext(
                "{urn:oasis:names:tc:emergency:cap:1.2}instruction"
            )
            or ""
        ).strip()
        result["severity"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}severity"
        )
        result["urgency"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}urgency"
        )
        result["certainty"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}certainty"
        )
        result["onset"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}onset"
        )
        result["expires"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}expires"
        )
        result["effective"] = info.findtext(
            "{urn:oasis:names:tc:emergency:cap:1.2}effective"
        )

        # Extract parameters
        for param in info.findall(
            "{urn:oasis:names:tc:emergency:cap:1.2}parameter"
        ):
            name = param.findtext(
                "{urn:oasis:names:tc:emergency:cap:1.2}valueName"
            )
            value = param.findtext(
                "{urn:oasis:names:tc:emergency:cap:1.2}value"
            )
            if name == "awareness_level" and value:
                # "1; green; Minor" → extract level number
                parts = value.split(";")
                if parts:
                    try:
                        result["awareness_level"] = int(parts[0].strip())
                    except ValueError:
                        pass

        break  # Only need Slovenian info

    return result


async def fetch_warnings(
    session: aiohttp.ClientSession,
    region: str,
) -> dict[str, Any]:
    """Fetch all weather warnings for a region.

    Args:
        session: aiohttp client session
        region: warning region ID (e.g. "SLOVENIA_MIDDLE")

    Returns::

        {
            "region": "SLOVENIA_MIDDLE",
            "region_name": "Osrednja Slovenija",
            "updated": "2026-03-12T09:09:44+01:00",
            "warnings": [
                {
                    "type": "wind",
                    "type_name": "Veter",
                    "level": 3,
                    "level_color": "oranžna",
                    "level_text": "Velika ogroženost",
                    "title": "Veter - velika ogroženost...",
                    "description": "Pričakujemo...",
                    "instruction": "Priporočamo...",
                    "onset": "...",
                    "expires": "...",
                    "updated": "...",
                },
            ],
        }
    """
    # Step 1: Fetch ATOM feed (1 request for all types)
    atom_url = ATOM_URL.format(region=region)
    try:
        async with session.get(atom_url) as response:
            response.raise_for_status()
            atom_text = await response.text()
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching warnings ATOM: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch warnings: {err}") from err

    # Parse ATOM
    try:
        atom_root = ET.fromstring(atom_text)
    except ET.ParseError as err:
        raise ArsoApiError(f"Failed to parse warnings ATOM: {err}") from err

    feed_updated = atom_root.findtext("{http://www.w3.org/2005/Atom}updated")
    atom_warnings = _parse_atom_feed(atom_text)

    # Step 2: For warnings with level >= 2, fetch CAP XML for details
    result_warnings: list[dict[str, Any]] = []
    for warning in atom_warnings:
        if warning["level"] >= 2:
            # Fetch detailed CAP XML
            cap_url = warning.get("cap_url", "")
            if cap_url:
                try:
                    async with session.get(cap_url) as resp:
                        resp.raise_for_status()
                        cap_text = await resp.text()
                    cap_data = _parse_cap_xml(cap_text)
                    warning.update({
                        "description": cap_data.get("description", ""),
                        "instruction": cap_data.get("instruction", ""),
                        "onset": cap_data.get("onset"),
                        "expires": cap_data.get("expires"),
                        "severity": cap_data.get("severity"),
                        "urgency": cap_data.get("urgency"),
                        "certainty": cap_data.get("certainty"),
                    })
                except Exception:
                    _LOGGER.debug(
                        "Failed to fetch CAP for %s", warning["type"],
                        exc_info=True,
                    )
            result_warnings.append(warning)

    # Sort by level descending (most severe first)
    result_warnings.sort(key=lambda w: w["level"], reverse=True)

    return {
        "region": region,
        "region_name": WARNING_REGIONS.get(region, region),
        "updated": feed_updated,
        "warnings": result_warnings,
    }
