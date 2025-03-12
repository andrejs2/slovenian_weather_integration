
"""
AQI senzor za ARSO – Air Quality Sensor

Ta modul pridobi podatke o kakovosti zraka iz ARSO XML vira in ustvari senzor,
ki je del platforme sensor in je pripet na isto napravo kot ARSO Weather entiteta.
Podatki se obdelajo z RS klasifikacijo in senzor prikaže AQI kategorijo ter
atribute (vrednosti posameznih onesnaževalcev).
"""

import aiohttp
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

# Uvozi tipov iz Home Assistant
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .helpers import normalize_location
from .const import DOMAIN 

_LOGGER = logging.getLogger(__name__)

# ARSO XML URL za zadnje urne podatke o kakovosti zraka
ARSO_AIR_QUALITY_URL = "http://www.arso.gov.si/xml/zrak/ones_zrak_urni_podatki_zadnji.xml"

# Preslikava merilnih postaj (ARSO) na Home Assistant lokacije.
STATION_MAPPING = {
    "Ljubljana": ["LJ Bežigrad", "LJ Celovška", "LJ Vič"],
    "Maribor": ["MB Titova", "MB Vrbanski"],
    "Celje": ["CE bolnica", "CE Ljubljanska"],
    "Bilje pri Novi Gorici": ["NG Grčna"],
    "Koper": ["Koper"],
    "Kranj": ["Kranj"],
    "Novo mesto": ["Novo mesto"],
    "Murska Sobota": ["MS Cankarjeva", "MS Rakičan"],
    "Ptuj": ["Ptuj"],
    "Trbovlje": ["Trbovlje"],
    "Zagorje": ["Zagorje"],
    "Hrastnik": ["Hrastnik"],
    "Črnomelj": ["Črnomelj Loka"],
    "Ilirska Bistrica": ["I.Bistrica Gregorčičeva"],
    "Iskrba": ["Iskrba"],
    "Krvavec": ["Krvavec"],
    "Otlica": ["Otlica"],
}

# Onesnaževalci, za katere zbiram podatke
POLLUTANTS = ["pm10", "pm2.5", "so2", "co", "o3", "no2", "benzen"]

def compute_sub_index_rs(value: float, breakpoints: list) -> int:
    """Vrne podindeks (1-5) za vrednost onesnaževalca glede na RS mejne vrednosti."""
    for i, bp in enumerate(breakpoints):
        if value <= bp:
            return i + 1
    return 5

def compute_overall_aqi_rs(data: dict) -> (int, str):
    """
    Izračuna celotni AQI kot maksimum podindeksov in pripadajočo kategorijo.
    RS lestvica:
      1 = Good, 2 = Moderate, 3 = Unhealthy for sensitive groups,
      4 = Unhealthy, 5 = Very Unhealthy.
    """
    sub_indices = []
    RS_POLLUTANT_BREAKPOINTS = {
        "pm2.5": [10, 20, 25, 50, 75],
        "pm10": [20, 50, 75, 100, 150],
        "o3": [120, 180, 240, 300, 380],
        "no2": [40, 80, 150, 200, 340],
        "co": [2, 4, 6, 8, 12],
        "so2": [20, 40, 60, 100, 750],
    }
    for pollutant, breakpoints in RS_POLLUTANT_BREAKPOINTS.items():
        value = data.get(pollutant)
        if value is not None:
            try:
                value = float(value)
                sub_index = compute_sub_index_rs(value, breakpoints)
                sub_indices.append(sub_index)
            except ValueError:
                _LOGGER.warning("Invalid value for %s: %s", pollutant, value)
    overall_index = max(sub_indices) if sub_indices else None
    if overall_index is None:
        category = "Ni podatka"
    elif overall_index == 1:
        category = "Zelo dobra"
    elif overall_index == 2:
        category = "Dobra"
    elif overall_index == 3:
        category = "Sprejemljiva"
    elif overall_index == 4:
        category = "Slaba"
    elif overall_index == 5:
        category = "Zelo slaba"
    else:
        category = "Izredno slaba"
    return overall_index, category

async def fetch_air_quality_data() -> dict:
    """Asinhrono pridobi podatke o kakovosti zraka iz ARSO XML vira."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_AIR_QUALITY_URL) as response:
                if response.status != 200:
                    _LOGGER.error("Error fetching ARSO Air Quality data: HTTP %s", response.status)
                    return None

                content = await response.text()
                root = ET.fromstring(content)
                air_quality_data = {}

                # Priprava podatkov za vsako lokacijo iz STATION_MAPPING
                temp_values = {
                    normalize_location(loc): {poll: [] for poll in POLLUTANTS}
                    for loc in STATION_MAPPING.keys()
                }

                for postaja in root.findall("postaja"):
                    ime = postaja.find("merilno_mesto").text.strip()
                    for ha_location, arso_locations in STATION_MAPPING.items():
                        if ime in arso_locations:
                            ha_location_norm = normalize_location(ha_location)
                            for pollutant in POLLUTANTS:
                                elem = postaja.find(pollutant)
                                if elem is not None and elem.text:
                                    try:
                                        value = float(elem.text)
                                        temp_values[ha_location_norm][pollutant].append(value)
                                    except ValueError:
                                        _LOGGER.warning("Invalid value for %s at %s: %s", pollutant, ime, elem.text)
                # Izračun povprečij za vsako lokacijo
                for location, pollutants in temp_values.items():
                    air_quality_data[location] = {}
                    for pollutant, values in pollutants.items():
                        if values:
                            air_quality_data[location][pollutant] = round(sum(values) / len(values), 1)
                        else:
                            air_quality_data[location][pollutant] = None
                _LOGGER.debug("Final air quality data: %s", air_quality_data)
                return air_quality_data
        except Exception as e:
            _LOGGER.error("Error processing ARSO Air Quality data: %s", e, exc_info=True)
            return None

class ArsoAirQualitySensor(Entity):
    """
    Senzor za kakovost zraka (AQI) – prikazuje celotni AQI po RS klasifikaciji
    in ima dodatne atribute z vrednostmi posameznih onesnaževalcev.
    """
    def __init__(self, hass: HomeAssistant, location: str):
        """Inicializacija AQI senzorja."""
        self._hass = hass
        self._location = location
        self._state = None
        self._attributes = {}

    async def async_update(self):
        """Osveži podatke o kakovosti zraka in nastavi stanje ter atribute senzorja."""
        data = await fetch_air_quality_data()
        location_norm = normalize_location(self._location)
        if data and location_norm in data:
            aqi_data = data[location_norm]
            overall_index, category = compute_overall_aqi_rs(aqi_data)
            self._state = category
            self._attributes = {
                "overall_index": overall_index,
                **aqi_data,
                "attribution": "Vir: Agencija RS za okolje"
            }
            _LOGGER.debug("Air Quality sensor for %s updated: %s, attributes: %s",
                          self._location, self._state, self._attributes)
        else:
            self._state = "No data"
            self._attributes = {}
            _LOGGER.warning("No air quality data available for %s", self._location)

    @property
    def name(self):
        """Vrne ime senzorja, tako da se prikaže kot 'sensor.air_quality_<lokacija>'."""
        return f"Air Quality {self._location}"

    @property
    def unique_id(self):
        """Vrne edinstven ID senzorja."""
        return f"air_quality_{normalize_location(self._location)}"

    @property
    def state(self):
        """Vrne trenutno stanje senzorja (AQI kategorija)."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Vrne dodatne atribute senzorja."""
        return self._attributes

    @property
    def icon(self):
        """Vrne ikono senzorja."""
        return "mdi:air-filter"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO vremenska postaja - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Vremenski podatki",
            "entry_type": "service",
        }

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> bool:
    """Inicializira AQI senzor na podlagi config entry."""
    location = config_entry.data.get("location")
    if not location:
        _LOGGER.error("No location found in config entry for ARSO Air Quality sensor")
        return False
    async_add_entities([ArsoAirQualitySensor(hass, location)])
    return True
