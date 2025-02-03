"""
sensor.py - ARSO Weather integration

Ta datoteka vsebuje implementacijo senzorjev za kakovost zraka in vremenskih parametrov.
Sedaj se celotni AQI izračuna na podlagi slovenskih mejnih vrednosti (RS).
"""

import logging
import asyncio  # RS MOD: Uvozimo asyncio za uporabo sleep
from asyncio import sleep
from urllib.parse import quote

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .helpers import async_remove_sensors
from .sun import fetch_sunshine_hours
from .utci import async_setup_entry as setup_utci_sensor, fetch_utci_data
from .air import fetch_air_quality_data, normalize_location
import xml.etree.ElementTree as ET

from .pollen import fetch_pollen_data


_LOGGER = logging.getLogger(__name__)

# --- Konstante za vremenske senzorje ---
SENSOR_TYPES = {
    "temperature": ["Temperature", "°C", "mdi:thermometer", "temperature"],
    "humidity": ["Humidity", "%", "mdi:water-percent", "humidity"],
    "pressure": ["Pressure", "hPa", "mdi:gauge", "pressure"],
    "wind_speed": ["Wind Speed", "km/h", "mdi:weather-windy", None],
    "wind_bearing": ["Wind Bearing", None, "mdi:compass", None],
    "wind_gust_speed": ["Wind Gust Speed", "km/h", "mdi:weather-windy-variant", None],
    "condition": ["Condition", None, "mdi:weather-cloudy", None],
    "weather_phenomenon": ["Weather Phenomenon", None, "mdi:weather-partly-rainy", None],
    "snow_accumulation": ["Snowfall", "mm", "mdi:snowflake", None],
    "precipitation": ["Rainfall", "mm", "mdi:weather-rainy", None],
    "cloud_base": ["Cloud base height", None, "mdi:cloud-outline", None],
    "pressure_tendency": ["Pressure Tendency", None, "mdi:gauge", None],
    "cloud_coverage": ["Cloud Coverage", "%", "mdi:cloud", None],
    "dew_point": ["Dew Point", "°C", "mdi:thermometer", None],
    "visibility": ["Visibility", "km", "mdi:eye", None],
    "sunshine_hours": ["Sunshine Hours", "h", "mdi:weather-sunny", None],
    "native_apparent_temperature": ["Apparent Temperature", "°C", "mdi:thermometer", "temperature"],
}

CLOUD_COVERAGE_MAP = {
    "jasno": 0,
    "pretežno jasno": 12.5,
    "delno jasno": 25,
    "delno oblačno": 50,
    "zmerno oblačno": 62.5,
    "pretežno oblačno": 87.5,
    "oblačno": 100,
}

LOCATION_MAPPING = {
    "bilje_pri_novi_gorici": "bilje",
    "celje_medlog": "celje",
    "bovec_letalisce": "bovec",
    "cerklje_letalisce": "letalisce_cerklje_ob_krki",
    "crnomelj_doblice": "crnomelj",
    "ljubljana_bezigrad": "ljubljana",
    "murska_sobota_rakican": "murska_sobota",
    "portoroz_letalisce": "letalisce_portoroz",
}

OZONE_CATEGORIES = [
    (50, "ZELO DOBRA"),
    (100, "DOBRA"),
    (130, "SPREJEMLJIVA"),
    (240, "SLABA"),
    (380, "ZELO SLABA"),
    (float("inf"), "IZREDNO SLABA"),
]

# --- RS MOD: Novo – mejne vrednosti za onesnaževalce po RS lestvici (5-stopenjska klasifikacija) ---
# Vsak seznam vsebuje zgornjo mejo za stopnjo 1 (Dobro) do 4 (Zelo slabo); vrednosti nad zadnjo mejo so "Nevarno".
RS_POLLUTANT_BREAKPOINTS = {
    "pm10":   [50, 75, 100, 150],      # 1: ≤50, 2: 51–75, 3: 76–100, 4: 101–150, 5: >150
    "pm2.5":  [25, 37, 50, 75],         # 1: ≤25, 2: 26–37, 3: 38–50, 4: 51–75, 5: >75
    "o3":     [120, 180, 240, 300],      # 1: ≤120, 2: 121–180, 3: 181–240, 4: 241–300, 5: >300
    "no2":    [40, 80, 150, 200],        # 1: ≤40, 2: 41–80, 3: 81–150, 4: 151–200, 5: >200
    "co":     [2, 4, 6, 8],              # 1: ≤2, 2: 2.1–4, 3: 4.1–6, 4: 6.1–8, 5: >8  (v ppm)
    "so2":    [20, 40, 60, 100],         # 1: ≤20, 2: 21–40, 3: 41–60, 4: 61–100, 5: >100
    # "benzen": ni določeno, zato ga ne obravnavamo
}

# Funkcija za izračun podindeksa na RS lestvici
def compute_sub_index_rs(value: float, breakpoints: list) -> int:
    """Return sub-index (1-5) for a pollutant value based on RS breakpoints."""
    for i, bp in enumerate(breakpoints):
        if value <= bp:
            return i + 1
    return 5  # Če je vrednost nad vsemi mejami

# Funkcija za izračun celotnega AQI in pripadajoče kategorije na RS lestvici
def compute_overall_aqi_rs(data: dict) -> (int, str):
    """
    Izračuna celotni AQI kot maksimum podindeksov za izbrane onesnaževalce
    in preslika ta indeks v kvalitativno kategorijo na RS lestvici.
    """
    sub_indices = []
    for pollutant, breakpoints in RS_POLLUTANT_BREAKPOINTS.items():
        value = data.get(pollutant)
        if value is not None:
            try:
                value = float(value)
                sub_index = compute_sub_index_rs(value, breakpoints)
                sub_indices.append(sub_index)
            except ValueError:
                _LOGGER.warning("⚠️ Neveljavna vrednost za %s: %s", pollutant, value)
    if not sub_indices:
        overall_index = None
    else:
        overall_index = max(sub_indices)
    
    # Preslikava celotnega indeksa v kategorijo na RS lestvici:
    # 1 = Dobro, 2 = Zmerno, 3 = Slabo, 4 = Zelo slabo, 5 = Nevarno
    if overall_index is None:
        category = "Ni podatkov"
    elif overall_index == 1:
        category = "Dobro"
    elif overall_index == 2:
        category = "Zmerno"
    elif overall_index == 3:
        category = "Slabo"
    elif overall_index == 4:
        category = "Zelo slabo"
    else:
        category = "Nevarno"
    return overall_index, category

# ------------------------------------------------------------------
# async_setup_entry: Inicializacija senzorjev
# ------------------------------------------------------------------
async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up ARSO Weather, Air Quality, and Pollen sensors."""
    
    entities = []

    # Pravilno dodamo pollen senzor (globalen, ni vezan na lokacijo)
    entities.append(ArsoPollenSensor())

    # Pridobimo lokacijo iz nastavitev
    location = config_entry.data.get("location")

    # Pridobimo podatke o kakovosti zraka
    air_quality_data = await fetch_air_quality_data()

    if location:
        location_normalized = normalize_location(location)

        # Ustvarimo senzor za AQI, če imamo podatke
        if air_quality_data and location_normalized in air_quality_data:
            _LOGGER.info("✅ Dodajam senzor kakovosti zraka za %s", location)
            sensor = ArsoAirQualitySensor(hass, location, air_quality_data)
            entities.append(sensor)
        else:
            _LOGGER.warning("⚠️ Ni podatkov o kakovosti zraka za %s", location)

    # Pridobimo seznam spremljanih vremenskih parametrov
    monitored_conditions = config_entry.data.get("monitored_conditions", list(SENSOR_TYPES.keys()))
    if "sunshine_hours" not in monitored_conditions:
        monitored_conditions.append("sunshine_hours")

    if monitored_conditions:
        for sensor_type in monitored_conditions:
            entities.append(ArsoWeatherSensor(hass, location, sensor_type, monitored_conditions))
    else:
        _LOGGER.warning("⚠️ Ni določenih monitored_conditions za %s", location)

    # Dodamo še UTCI senzor
    await setup_utci_sensor(hass, config_entry, async_add_entities)

    _LOGGER.info("✅ Skupno dodajam %d senzorjev", len(entities))
    async_add_entities(entities, True)


# ------------------------------------------------------------------
# ArsoAirQualitySensor: Senor za celotni AQI (RS lestvica)
# ------------------------------------------------------------------
class ArsoAirQualitySensor(Entity):
    """Reprezentacija ARSO senzorja za kakovost zraka z RS klasifikacijo AQI."""

    def __init__(self, hass, location, air_quality_data: dict):
        """Inicializacija senzorja za kakovost zraka."""
        self._hass = hass
        self._location = location
        self._state = None  # V state shranimo kategorijo (npr. "Dobro", "Zmerno", ...)
        self._attributes = {}
        _LOGGER.info("📡 Inicializacija senzorja za kakovost zraka: %s", location)
        self.update_air_quality_data(air_quality_data)

    def update_air_quality_data(self, air_quality_data: dict):
        """Posodobi podatke o kakovosti zraka in izračunaj celotni AQI na RS lestvici."""
        _LOGGER.debug("📊 Air quality data received: %s", air_quality_data)
        location_normalized = normalize_location(self._location)
        if not air_quality_data or location_normalized not in air_quality_data:
            _LOGGER.warning("⚠️ Ni podatkov o kakovosti zraka za %s (normalized: %s)", self._location, location_normalized)
            self._state = "Ni podatkov"
            return

        data = air_quality_data.get(location_normalized, {})
        overall_index, category = compute_overall_aqi_rs(data)  # RS MOD: Uporabimo RS funkcijo
        self._state = category
        self._attributes = {
            "overall_index": overall_index,
            "PM10": data.get("pm10", "Ni podatkov"),
            "PM2.5": data.get("pm2.5", "Ni podatkov"),
            "O3": data.get("o3", "Ni podatkov"),
            "NO2": data.get("no2", "Ni podatkov"),
            "CO": data.get("co", "Ni podatkov"),
            "SO2": data.get("so2", "Ni podatkov"),
            "Benzen": data.get("benzen", "Ni podatkov"),
            "attribution": "Vir: Agencija RS za okolje",
        }
        _LOGGER.info("✅ Posodobljeni podatki za senzor kakovosti zraka (%s): %s", self._location, self._attributes)

    async def async_update(self):
        """Pridobi najnovejše podatke o kakovosti zraka."""
        _LOGGER.debug("🔄 Posodobitev podatkov za kakovost zraka: %s", self._location)
        air_quality_data = await fetch_air_quality_data()
        if air_quality_data:
            self.update_air_quality_data(air_quality_data)
        else:
            _LOGGER.warning("⚠️ Air quality data is empty or None!")

    @property
    def unique_id(self):
        """Vrne unikatni ID za senzor."""
        return f"arso_weather_{normalize_location(self._location)}_air_quality"  # RS MOD

    @property
    def name(self):
        """Vrne ime senzorja."""
        return f"ARSO Weather {self._location.capitalize()} - Air Quality"

    @property
    def state(self):
        """Vrne stanje senzorja, tj. AQI kategorijo."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Vrne dodatne atribute senzorja."""
        return self._attributes

    @property
    def device_info(self):
        """Return device information to group sensors."""
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

# ------------------------------------------------------------------
# ArsoWeatherSensor: Senor za vremenske podatke
# ------------------------------------------------------------------
class ArsoWeatherSensor(Entity):
    """Representation of an ARSO Weather sensor."""

    def __init__(self, hass, location, sensor_type, monitored_conditions: list):
        """Initialize the Weather sensor."""
        self._hass = hass
        self._location = location.replace("_", " ")
        self._sensor_type = sensor_type
        self._monitored_conditions = monitored_conditions
        self._attr_name = f"ARSO Weather {location.capitalize()} - {SENSOR_TYPES[sensor_type][0]}"
        self._attr_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._icon = SENSOR_TYPES[sensor_type][2]
        self._device_class = SENSOR_TYPES[sensor_type][3]
        self._state = None

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return f"arso_weather_{self._location.lower()}_{self._sensor_type}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._attr_name

    @property
    def state(self):
        """Return the current state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._attr_unit_of_measurement

    @property
    def icon(self):
        """Return the icon for the sensor."""
        return self._icon

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def available(self):
        """Return if the sensor is available."""
        return self._state is not None

    @property
    def extra_state_attributes(self):
        """Return extra state attributes."""
        return {}

    @property
    def device_info(self):
        """Return device information to group sensors."""
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return True if the sensor should be enabled by default."""
        return True

    async def async_update(self):
        """Update the weather sensor state with the latest data."""
        if self._sensor_type not in self._monitored_conditions:
            self._state = None
            return

        if self._sensor_type == "native_apparent_temperature":
            _LOGGER.info("🌡️ Fetching UTCI data for apparent temperature in %s...", self._location)
            self._state = await fetch_utci_data(self._hass, self._location)
            _LOGGER.info("✅ Apparent Temperature for %s: %s", self._location, self._state)
            return

        if self._sensor_type == "sunshine_hours":
            _LOGGER.info("🔆 Fetching sunshine hours for %s...", self._location)
            self._state = await fetch_sunshine_hours()
            _LOGGER.info("✅ Sunshine hours for %s: %s", self._location, self._state)
            return

        session = async_get_clientsession(self._hass)
        encoded_location = quote(self._location, safe="")
        api_url = f"https://vreme.arso.gov.si/api/1.0/location/?location={encoded_location}"

        if self._sensor_type in [
            "weather_phenomenon",
            "condition",
            "snow_accumulation",
            "precipitation",
            "cloud_base",
            "pressure_tendency",
            "cloud_coverage",
        ]:
            try:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        _LOGGER.warning("⚠️ Failed to fetch data for %s: HTTP %s", self._location, response.status)
                        self._state = None
                        return

                    data = await response.json()
                    forecast1h = data.get("forecast1h", {}).get("features", [])[0].get("properties", {}).get("days", [])
                    if not forecast1h:
                        _LOGGER.warning("⚠️ No forecast data available for %s", self._location)
                        self._state = None
                        return

                    timeline = forecast1h[0].get("timeline", [])
                    if not timeline:
                        _LOGGER.warning("⚠️ No timeline data available for %s", self._location)
                        self._state = None
                        return

                    current_forecast = timeline[0]
                    sensor_mapping = {
                        "weather_phenomenon": "clouds_shortText_wwsyn_shortText",
                        "condition": "clouds_shortText",
                        "snow_accumulation": "sn_acc",
                        "precipitation": "tp_acc",
                        "cloud_base": "cloudBase_shortText",
                        "pressure_tendency": "pa_shortText",
                        "cloud_coverage": "clouds_shortText"
                    }
                    if self._sensor_type in sensor_mapping:
                        key = sensor_mapping[self._sensor_type]
                        self._state = current_forecast.get(key, None)
                        if self._sensor_type == "cloud_coverage":
                            cloud_text = current_forecast.get("clouds_shortText", "jasno").lower()
                            self._state = CLOUD_COVERAGE_MAP.get(cloud_text, 0)
                    _LOGGER.debug("✅ Updated %s for %s: %s", self._sensor_type, self._location, self._state)
            except Exception as e:
                _LOGGER.error("❌ Error fetching data for %s: %s", self._location, e)
                self._state = None
        else:
            formatted_location = normalize_location(self._location)
            for _ in range(5):
                formatted_location = normalize_location(self._location)
                weather_entity = self._hass.states.get(f"weather.arso_weather_{formatted_location}")
                if weather_entity:
                    attributes = weather_entity.attributes
                    if self._sensor_type in attributes:
                        self._state = attributes[self._sensor_type]
                        _LOGGER.debug("✅ Updated attribute %s for %s: %s", self._sensor_type, self._location, self._state)
                    else:
                        self._state = None
                        _LOGGER.warning("⚠️ Attribute '%s' not found in weather entity for %s", self._sensor_type, self._location)
                    return
                _LOGGER.debug("⏳ Weather entity not found for %s. Retrying...", formatted_location)
                await sleep(2)
            _LOGGER.warning("⚠️ Weather entity for %s not found after retries.", formatted_location)
            self._state = None

class ArsoPollenSensor(Entity):
    """Senzor za cvetni prah iz ARSO (globalen, neodvisen od lokacije)."""

    def __init__(self):
        """Inicializacija senzora."""
        self._state = None  # Stanje (seznam rastlin)
        self._attributes = {}  # Dodatni atributi (podrobnosti o cvetnem prahu)

    @property
    def unique_id(self):
        """Vrne unikaten ID za senzor."""
        return "arso_weather_pollen"

    @property
    def name(self):
        """Vrne ime senzorja."""
        return f"ARSO Weather - Pollen"

    @property
    def state(self):
        """Vrne trenutno stanje senzorja (seznam rastlin)."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Vrne dodatne atribute senzorja (podrobnosti o cvetnem prahu)."""
        return self._attributes
    # @property
    # def device_info(self):
    #     """Vrne informacije o napravi, da bo senzor prikazan pod ARSO Weather napravo."""
    #     return {
    #         "identifiers": {(DOMAIN, "arso_weather")},
    #         "name": f"ARSO Weather Station - {self._location.title()}",
    #         "manufacturer": "ARSO",
    #         "model": "Weather Sensors",
    #         "entry_type": "service",
    #     }
    @property
    def device_info(self):
        """Vrne informacije o napravi, da bo senzor prikazan pod ARSO Weather napravo."""
        return {
            "identifiers": {(DOMAIN, "arso_weather")},
            "name": f"ARSO Weather Pollen Sensor",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    @property
    def icon(self):
        """Vrne ikono za prikaz v Home Assistant."""
        return "mdi:flower"

    async def async_update(self):
        """Posodobitev podatkov senzorja."""
        _LOGGER.debug("🔄 Posodabljam podatke za ARSO Pollen sensor...")
        
        data = await fetch_pollen_data()
        
        if data:
            self._state = data["state"]  # Seznam rastlin, ki cvetijo
            self._attributes = data["attributes"]  # Podrobnosti o cvetnem prahu
            _LOGGER.info("✅ ARSO Pollen senzor posodobljen: %s", self._state)
        else:
            _LOGGER.warning("⚠️ ARSO Pollen podatki niso na voljo!")
            self._state = "Ni podatkov"
            self._attributes = {}
