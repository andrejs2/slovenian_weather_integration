"""Client for fetching mountain weather forecasts from ARSO.

Provides two types of mountain data:
1. Text forecasts (today/tomorrow) from simple HTML pages.
2. Elevation-based forecasts from detailed HTML tables with temperature,
   wind, humidity, and stability data at various altitudes.
"""

from __future__ import annotations

import html as html_mod
import logging
import re

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

_MOUNTAIN_BASE = (
    "https://meteo.arso.gov.si/uploads/probase/www/fproduct/text/sl/"
)
MOUNTAIN_TODAY_URL = _MOUNTAIN_BASE + "fcast_SLOVENIA_MOUNTAINS_d1_text.html"
MOUNTAIN_TOMORROW_URL = _MOUNTAIN_BASE + "fcast_SLOVENIA_MOUNTAINS_d2_text.html"

MOUNTAIN_FORECAST_JSON_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/sproduct/mountain"
    "/assets/mountain/forecast_mountain.json"
)

_ELEVATION_BASE = _MOUNTAIN_BASE + "forecast_SI_{region_id}_long.html"

MOUNTAIN_REGIONS: dict[str, str] = {
    "Julijske Alpe": "JULIAN-ALPS",
    "JZ Julijske Alpe": "JULIAN-ALPS_SOUTH-WEST",
    "Kamniško-Savinjske Alpe": "KAMNIK-SAVINJA-ALPS",
    "Karavanke": "KARAVANKE-ALPS",
    "Pohorje": "POHORJE",
    "Snežnik": "SNEZNIK",
    "Škofjeloško hribovje": "SKOFJELOSKO-HRIBOVJE",
    "Vzhodnoslovensko hribovje": "EAST-MOUNTAINS",
}

# Reverse lookup: region_id -> display name
_REGION_ID_TO_NAME: dict[str, str] = {v: k for k, v in MOUNTAIN_REGIONS.items()}

# Elevations that appear in temperature/humidity rows
_ELEVATIONS = (5500, 3000, 2500, 2000, 1500, 1000, 500)

# Elevations that appear in weather icon rows
_WEATHER_ELEVATIONS = (2500, 1500)

# Elevations that appear in wind rows
_WIND_ELEVATIONS = (3000, 2500, 2000, 1500, 1000)


# ---------------------------------------------------------------------------
# Text forecasts (existing functionality)
# ---------------------------------------------------------------------------

async def fetch_mountain_forecast(session: aiohttp.ClientSession) -> dict:
    """Fetch mountain forecasts (today + tomorrow) from ARSO.

    Returns dict with keys: today, tomorrow, updated.
    """
    today_text, updated = await _fetch_and_parse(session, MOUNTAIN_TODAY_URL)
    tomorrow_text, _ = await _fetch_and_parse(session, MOUNTAIN_TOMORROW_URL)

    return {
        "today": today_text,
        "tomorrow": tomorrow_text,
        "updated": updated,
    }


async def fetch_mountain_forecast_json(
    session: aiohttp.ClientSession,
) -> dict:
    """Fetch structured mountain forecast from ARSO JSON endpoint.

    Returns dict with keys: datum, uvod, zakljucek.
    """
    _LOGGER.debug("Fetching mountain forecast JSON from %s", MOUNTAIN_FORECAST_JSON_URL)
    try:
        async with session.get(MOUNTAIN_FORECAST_JSON_URL) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)
            return {
                "datum": data.get("datum"),
                "uvod": data.get("uvod"),
                "zakljucek": data.get("zakljucek"),
            }
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching mountain forecast JSON: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(
            f"Failed to fetch mountain forecast JSON: {err}"
        ) from err


async def _fetch_and_parse(
    session: aiohttp.ClientSession, url: str
) -> tuple[str | None, str | None]:
    """Fetch HTML page and extract forecast text + timestamp."""
    html = await _fetch_html(session, url)
    return _parse_mountain_html(html)


def _parse_mountain_html(html: str) -> tuple[str | None, str | None]:
    """Extract forecast text and timestamp from mountain HTML page.

    HTML structure:
      <h2>Napoved za GORSKI SVET</h2>
      <p>Forecast text...</p>
      <sup>Vir: ...</sup>
      <sup>2026-03-11 05:51</sup>
    """
    match = re.search(r"<p>(.*?)</p>", html, re.DOTALL)
    text = match.group(1).strip() if match else None

    timestamps = re.findall(r"<sup>\s*([\d]{4}-[\d-]+\s+[\d:]+)\s*</sup>", html)
    updated = timestamps[-1].strip() if timestamps else None

    return text, updated


# ---------------------------------------------------------------------------
# Elevation-based forecasts (new functionality)
# ---------------------------------------------------------------------------

async def fetch_mountain_elevation_data(
    session: aiohttp.ClientSession, region_id: str
) -> dict:
    """Fetch elevation-based mountain forecast for a specific region.

    Args:
        session: An aiohttp client session.
        region_id: Region identifier (e.g. "JULIAN-ALPS"). Must be a value
            from ``MOUNTAIN_REGIONS``.

    Returns a dict with keys:
        region: Human-readable region name.
        timestamps: List of ISO-ish timestamp strings from the table.
        current: Dict with data for the first time slot.
        forecast: List of dicts for remaining time slots.
        updated: Calculation timestamp string from the table header row.
    """
    url = _ELEVATION_BASE.format(region_id=region_id)
    html = await _fetch_html(session, url)
    return _parse_elevation_html(html, region_id)


async def _fetch_html(
    session: aiohttp.ClientSession, url: str
) -> str:
    """Fetch an HTML page from ARSO."""
    _LOGGER.debug("Fetching mountain data from %s", url)
    try:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.text()
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching mountain forecast: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(
            f"Failed to fetch mountain forecast: {err}"
        ) from err


def _parse_elevation_html(html: str, region_id: str) -> dict:
    """Parse the elevation forecast HTML table into structured data.

    The table uses ``class`` attributes on ``<td>`` elements to encode
    ISO timestamps (e.g. ``class="2026-03-11 06:00:00"``).  Row labels
    in the first ``<td>`` identify the data type (elevation, zero
    isotherm, snow line, stability, etc.).  Sections are separated by
    sub-header rows whose first cell has class ``meteoSI-subHeader``.
    """
    region_name = _REGION_ID_TO_NAME.get(region_id, region_id)

    # Decode HTML entities so we work with clean text
    html = html_mod.unescape(html)

    # ---- Extract unique ordered timestamps from <td> class attributes ----
    timestamps = _extract_timestamps_from_html(html)

    # ---- Extract the "updated" / calculation time from the header row ----
    updated = _extract_updated_time(html)

    if not timestamps:
        _LOGGER.warning("No timestamps parsed for region %s", region_id)
        return _empty_result(region_name)

    # ---- Extract all <tr> blocks, keeping the full tag markup ----
    # We need the full <td ...> tags (not just content) so we can read class attrs.
    row_blocks = re.findall(r"<tr[^>]*>(.+?)</tr>", html, re.DOTALL)

    # Collected data: keyed by elevation, values are lists parallel to timestamps
    weather_icons: dict[int, list[str]] = {}
    temperatures: dict[int, list[int | None]] = {}
    wind_directions: dict[int, list[str]] = {}
    wind_speeds: dict[int, list[int | None]] = {}
    humidity: dict[int, list[int | None]] = {}
    zero_isotherm: list[int | None] = []
    snow_line: list[int | None] = []
    stability: list[str | None] = []

    # Track which section we are in based on sub-header rows
    current_section: str | None = None

    for row_html in row_blocks:
        # Extract full <td ...>content</td> pairs (tag + content)
        td_pairs = re.findall(
            r"(<td[^>]*>)(.*?)</td>", row_html, re.DOTALL
        )
        if not td_pairs:
            continue

        first_tag, first_content = td_pairs[0]
        first_text = _strip_tags(first_content).strip()
        lower_first = first_text.lower()

        # --- Skip timestamp header row (already parsed globally) ---
        if "izra" in lower_first:
            continue

        # --- Separator rows (all cells empty or whitespace) ---
        if _is_separator_row_pairs(td_pairs):
            continue

        # --- Section sub-headers ---
        if "meteoSI-subHeader" in first_tag:
            if "vreme" in lower_first:
                current_section = "weather"
                # The sub-header row itself may contain weather icons
                elevation = _extract_elevation_from_label(first_text)
                if elevation is not None:
                    weather_icons[elevation] = _extract_weather_icons_pairs(
                        td_pairs[1:]
                    )
            elif "temperatura" in lower_first or "temp" in lower_first:
                current_section = "temp"
            elif "veter" in lower_first:
                current_section = "wind"
            elif "vlaga" in lower_first or "vlažnost" in lower_first:
                current_section = "humidity"
            continue

        # Also detect sub-headers by class in the row itself
        if "subHeader" in first_tag and "meteoSI-subHeader" not in first_tag:
            if "temperatura" in lower_first or "temp" in lower_first:
                current_section = "temp"
            elif "veter" in lower_first:
                current_section = "wind"
            elif "vlaga" in lower_first or "vlažnost" in lower_first:
                current_section = "humidity"
            continue

        data_cells = td_pairs[1:]

        # --- Weather icon rows: "Vreme na XXXX m" ---
        if "vreme na" in lower_first:
            elevation = _extract_elevation_from_label(first_text)
            if elevation is not None:
                weather_icons[elevation] = _extract_weather_icons_pairs(
                    data_cells
                )
            continue

        # Within weather section, rows with "na XXXX m" are also icon rows
        if current_section == "weather":
            elevation = _extract_elevation_from_label(first_text)
            if elevation is not None:
                weather_icons[elevation] = _extract_weather_icons_pairs(
                    data_cells
                )
                continue

        # --- Zero isotherm: "Višina ničte izoterme" ---
        if "izoterm" in lower_first:
            zero_isotherm = _extract_altitude_values_pairs(data_cells)
            continue

        # --- Snow line: "Meja sneženja" ---
        if "meja" in lower_first and "sne" in lower_first:
            snow_line = _extract_altitude_values_pairs(data_cells)
            continue

        # --- Stability: "Stabilnost" ---
        if "stabilnost" in lower_first or "stabil" in lower_first:
            stability = [
                _strip_tags(content).strip() or None
                for _, content in data_cells
            ]
            continue

        # --- Elevation data rows: "na XXXX m" ---
        elevation = _extract_elevation_from_label(first_text)
        if elevation is not None:
            if current_section == "temp":
                temperatures[elevation] = _extract_numeric_values_pairs(
                    data_cells
                )
            elif current_section == "wind":
                # Direction rows have <img> tags, speed rows have numbers
                if any("<img" in content for _, content in data_cells):
                    wind_directions[elevation] = _extract_icon_names_pairs(
                        data_cells
                    )
                else:
                    wind_speeds[elevation] = _extract_numeric_values_pairs(
                        data_cells
                    )
            elif current_section == "humidity":
                humidity[elevation] = _extract_numeric_values_pairs(
                    data_cells
                )
            continue

        # --- Wind speed rows without elevation label ---
        if current_section == "wind":
            combined = " ".join(content for _, content in data_cells)
            if "km/h" in combined:
                # Assign to the first direction elevation that lacks speed data
                for elev in _WIND_ELEVATIONS:
                    if elev in wind_directions and elev not in wind_speeds:
                        wind_speeds[elev] = _extract_numeric_values_pairs(
                            data_cells
                        )
                        break

    # ---- Build per-slot dicts ----
    n_slots = len(timestamps)
    all_slots: list[dict] = []

    for i in range(n_slots):
        slot: dict = {"valid": timestamps[i]}

        # Temperatures at each elevation
        for elev in _ELEVATIONS:
            val = _safe_index(temperatures.get(elev), i)
            if val is not None:
                slot[f"temp_{elev}m"] = val

        # Weather conditions
        for elev in _WEATHER_ELEVATIONS:
            val = _safe_index_str(weather_icons.get(elev), i)
            if val is not None:
                slot[f"conditions_{elev}m"] = val

        # Wind speed and direction
        for elev in _WIND_ELEVATIONS:
            spd = _safe_index(wind_speeds.get(elev), i)
            if spd is not None:
                slot[f"wind_{elev}m_kmh"] = spd
            direction = _safe_index_str(wind_directions.get(elev), i)
            if direction is not None:
                slot[f"wind_{elev}m_dir"] = direction

        # Humidity
        for elev in _ELEVATIONS:
            val = _safe_index(humidity.get(elev), i)
            if val is not None:
                slot[f"humidity_{elev}m"] = val

        # Zero isotherm
        val = _safe_index(zero_isotherm, i)
        if val is not None:
            slot["zero_isotherm_m"] = val

        # Snow line
        val = _safe_index(snow_line, i)
        if val is not None:
            slot["snow_line_m"] = val

        # Stability
        stab = _safe_index_str(stability, i)
        if stab:
            slot["stability"] = stab

        all_slots.append(slot)

    # Split: first slot is "current", rest are "forecast"
    current = {k: v for k, v in all_slots[0].items() if k != "valid"}
    forecast = all_slots[1:] if len(all_slots) > 1 else []

    return {
        "region": region_name,
        "timestamps": timestamps,
        "current": current,
        "forecast": forecast,
        "updated": updated,
    }


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _extract_timestamps_from_html(html: str) -> list[str]:
    """Extract unique ordered timestamps from ``<td>`` class attributes.

    The ARSO table encodes each time slot as a class on the ``<td>`` element,
    e.g. ``<td class="2026-03-11 06:00:00">``.  We collect all unique values
    in order of first appearance.
    """
    matches = re.findall(
        r'<td[^>]*\bclass="(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})"',
        html,
    )
    seen: set[str] = set()
    result: list[str] = []
    for ts in matches:
        if ts not in seen:
            seen.add(ts)
            result.append(ts)
    return result


def _extract_updated_time(html: str) -> str | None:
    """Extract the calculation / "Izračun" timestamp from the table.

    Looks for text like "Izračun: Sreda, 11.03.2026 01 CET" inside
    a ``<td>`` whose content contains "Izra" (beginning of "Izračun").
    """
    # Match any <td> whose content includes the calculation label
    m = re.search(
        r"<td[^>]*>(.*?Izra.*?)</td>",
        html,
        re.DOTALL,
    )
    if not m:
        return None
    text = _strip_tags(html_mod.unescape(m.group(1))).strip()
    # Pull out the date portion: "11.03.2026 01 CET"
    dm = re.search(r"(\d{2}\.\d{2}\.\d{4}\s+\d+\s*\w+)", text)
    return dm.group(1).strip() if dm else text


def _extract_elevation_from_label(label: str) -> int | None:
    """Extract elevation in metres from a label like ``na 2500 m``."""
    m = re.search(r"(?:na\s+)?(\d{3,5})\s*m\b", label)
    return int(m.group(1)) if m else None


def _extract_weather_icons_pairs(
    pairs: list[tuple[str, str]],
) -> list[str]:
    """Extract weather icon names from ``(tag, content)`` pairs."""
    result: list[str] = []
    for _, content in pairs:
        m = re.search(r'<img[^>]+src="[^"]*?/([^/"]+)\.png"', content)
        result.append(m.group(1) if m else "")
    return result


def _extract_icon_names_pairs(
    pairs: list[tuple[str, str]],
) -> list[str]:
    """Extract icon names (wind direction) from ``(tag, content)`` pairs."""
    return _extract_weather_icons_pairs(pairs)


def _extract_numeric_values_pairs(
    pairs: list[tuple[str, str]],
) -> list[int | None]:
    """Extract integer values from cell content.

    Handles formats like ``-24 °C``, ``32 km/h``, ``90 %``.
    """
    result: list[int | None] = []
    for _, content in pairs:
        text = _strip_tags(content).strip()
        m = re.search(r"(-?\d+)", text)
        result.append(int(m.group(1)) if m else None)
    return result


def _extract_altitude_values_pairs(
    pairs: list[tuple[str, str]],
) -> list[int | None]:
    """Extract altitude values in metres from cells like ``1835 m``."""
    result: list[int | None] = []
    for _, content in pairs:
        text = _strip_tags(content).strip()
        m = re.search(r"(\d+)\s*m", text)
        result.append(int(m.group(1)) if m else None)
    return result


def _strip_tags(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", "", text)


def _is_separator_row_pairs(
    pairs: list[tuple[str, str]],
) -> bool:
    """Check if all cells in a row are empty or whitespace-only."""
    for _, content in pairs:
        stripped = _strip_tags(content).strip()
        if stripped and stripped != "\xa0":
            return False
    return True


def _safe_index(lst: list | None, idx: int) -> int | None:
    """Safely get an integer value from a list by index."""
    if lst is None or idx >= len(lst):
        return None
    return lst[idx]


def _safe_index_str(lst: list | None, idx: int) -> str | None:
    """Safely get a string value from a list by index."""
    if lst is None or idx >= len(lst):
        return None
    val = lst[idx]
    return val if val else None


def _empty_result(region_name: str) -> dict:
    """Return an empty result dict when parsing fails."""
    return {
        "region": region_name,
        "timestamps": [],
        "current": {},
        "forecast": [],
        "updated": None,
    }
