"""Client for fetching ski resort weather data from ARSO."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import aiohttp

from .client import ArsoApiError

_LOGGER = logging.getLogger(__name__)

SKI_FORECAST_URL = (
    "https://vreme.arso.gov.si/uploads/probase/www/fproduct/text/sl/"
    "forecast_si-mountain_latest.xml"
)

# All 46 Slovenian ski resorts from the XML feed.
# Mapping: display name -> XML domain_title (uppercase key used in data).
SKI_RESORTS: dict[str, str] = {
    "Bohinj": "BOHINJ",
    "Bukovnik": "BUKOVNIK",
    "Celjska koča": "CELJSKA KOCA",
    "Cerkno": "CERKNO",
    "Črmošnjice": "CRMOSNJICE",
    "Črna na Koroškem": "CRNA NA KOROSKEM",
    "Črni vrh nad Idrijo": "CRNI VRH NAD IDRIJO",
    "Dole pri Litiji": "DOLE PRI LITIJI",
    "Globoki Klanec": "GLOBOKI KLANEC",
    "Golte": "GOLTE",
    "Ivarčko pod Uršljo goro": "IVARCKO POD URSLJO GORO ",
    "Izver pri Sodražici": "IZVER PRI SODRAZICI",
    "Javornik pri Črnem vrhu nad Idrijo": "JAVORNIK PRI CRNEM VRHU NAD IDRIJO",
    "Jezersko": "JEZERSKO",
    "Kalič": "KALIC",
    "Kandrše": "KANDRSE",
    "Kanin": "KANIN",
    "Kobla": "KOBLA",
    "Kope": "KOPE",
    "Kranjska Gora": "KRANJSKA GORA",
    "Krvavec": "KRVAVEC",
    "Logarska dolina": "LOGARSKA DOLINA",
    "Macesnovec": "MACESNOVC",
    "Marela - Kisovec": "MARELA-KISOVEC",
    "Mariborsko Pohorje": "MARIBORSKO POHORJE",
    "Medvode": "MEDVODE",
    "Peca": "PECA",
    "Planica": "PLANICA",
    "Ravne na Koroškem": "RAVNE NA KOROSKEM",
    "Ribniška koča": "RIBNISKA KOCA",
    "Ribniško Pohorje": "RIBNISKO POHORJE",
    "Rogla": "ROGLA",
    "Rudno polje": "RUDNO POLJE",
    "Rudno v Selški dolini": "RUDNO V SELSKI DOLINI",
    "Šentjošt": "SENTJOST",
    "Sorišca planina": "SORISKA PLANINA",
    "Španov vrh": "SPANOV VRH",
    "Stari vrh nad Škofjo Loko": "STARI VRH NAD SKOFJO LOKO",
    "Straža na Bledu": "STRAZA NA BLEDU",
    "Šviščaki": "SVISCAKI",
    "Trije kralji na Pohorju": "TRIJE KRALJI NA POHORJU",
    "Ulovka": "ULOVKA",
    "Velika planina": "VELIKA PLANINA",
    "Vogel": "VOGEL",
    "Zatrnik": "ZATRNIK",
    "Zelenica": "ZELENICA",
}

# Reverse lookup: XML key -> display name
_XML_TO_DISPLAY: dict[str, str] = {v.strip(): k for k, v in SKI_RESORTS.items()}


async def fetch_ski_data(session: aiohttp.ClientSession) -> dict:
    """Fetch and parse ski resort weather from ARSO XML.

    Returns dict keyed by XML resort name (uppercase), each value is a dict:
      - "display_name": nice display name
      - "altitude": meters
      - "lat", "lon": coordinates
      - "current": dict with current conditions (first time slot)
      - "forecast": list of dicts for future time slots
      - "updated": timestamp string
    """
    try:
        async with session.get(SKI_FORECAST_URL) as response:
            response.raise_for_status()
            xml_text = await response.text()
    except aiohttp.ClientResponseError as err:
        raise ArsoApiError(
            f"HTTP {err.status} fetching ski data: {err.message}"
        ) from err
    except aiohttp.ClientError as err:
        raise ArsoApiError(f"Failed to fetch ski data: {err}") from err

    return _parse_ski_xml(xml_text)


def _parse_ski_xml(xml_text: str) -> dict:
    """Parse ski resort XML into structured data per resort."""
    root = ET.fromstring(xml_text)

    # Collect time slots per resort
    raw: dict[str, list[dict]] = {}
    for md in root.findall("metData"):
        name = _text(md, "domain_title")
        if not name:
            continue
        name = name.strip()

        slot = {
            "valid": _text(md, "valid"),
            "conditions": _text(md, "nn_shortText_domain_top"),
            "conditions_icon": _text(md, "nn_icon_domain_top"),
            "temperature": _int(md, "t_level_domain_top"),
            "windchill": _int(md, "windchill_level_domain_top"),
            "humidity": _int(md, "rh_level_domain_top"),
            "wind_direction": _text(md, "ddShortText_level_domain_top"),
            "wind_speed_kmh": _int(md, "ffVal_level_domain_top_kmh"),
            "wind_gust_kmh": _int(md, "ffmax_level_domain_top_kmh"),
            "precipitation": _text(md, "rr_decodeText_domain_top"),
            "weather_phenomena": _text(md, "wwsyn_decodeText_domain_top"),
            "thunderstorm": _text(md, "ts_shortText_domain_top"),
            "fog": _text(md, "fog_icon_domain_top") == "FG",
            "visibility_km": _float(md, "vis_level_domain_top"),
        }

        if name not in raw:
            raw[name] = []
            # Store metadata from first occurrence
            raw[name].append({
                "_meta": True,
                "display_name": _text(md, "domain_longTitle") or name,
                "altitude": _int(md, "domain_altitude"),
                "lat": _float(md, "domain_lat"),
                "lon": _float(md, "domain_lon"),
                "updated": _text(md, "tsUpdated"),
            })

        raw[name].append(slot)

    # Build final structure
    result: dict[str, dict] = {}
    for resort_key, entries in raw.items():
        meta = entries[0]  # _meta entry
        slots = [e for e in entries[1:]]  # time-slot entries

        result[resort_key] = {
            "display_name": meta.get("display_name", resort_key),
            "altitude": meta.get("altitude"),
            "lat": meta.get("lat"),
            "lon": meta.get("lon"),
            "updated": meta.get("updated"),
            "current": slots[0] if slots else {},
            "forecast": slots[1:] if len(slots) > 1 else [],
        }

    return result


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    if child is not None and child.text and child.text.strip() != "None":
        return child.text.strip()
    return None


def _int(el: ET.Element, tag: str) -> int | None:
    val = _text(el, tag)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            return None
    return None


def _float(el: ET.Element, tag: str) -> float | None:
    val = _text(el, tag)
    if val is not None:
        try:
            return float(val)
        except ValueError:
            return None
    return None
