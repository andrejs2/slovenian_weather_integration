
import logging
import asyncio
from asyncio import sleep
from urllib.parse import quote

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .helpers import async_remove_sensors, normalize_location

from .utci import async_setup_entry as setup_utci_sensor, fetch_utci_data
from .air import fetch_air_quality_data
from .pollen import fetch_pollen_data, fetch_pollen_forecast

from .agro import fetch_agro_data, ArsoAgroSensor, ArsoAgroSunSensor, normalize_location as normalize_agro_location, AGRO_STATION_MAPPING
import xml.etree.ElementTree as ET

_LOGGER = logging.getLogger(__name__)

# Konstante za vremenske senzorje
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
    "sun_duration": ["Sun Duration", "h", "mdi:weather-sunny", None],
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

# RS MOD: mejne vrednosti za onesnaževalce po RS lestvici
RS_POLLUTANT_BREAKPOINTS = {
    "pm10":   [50, 75, 100, 150],
    "pm2.5":  [25, 37, 50, 75],
    "o3":     [120, 180, 240, 300],
    "no2":    [40, 80, 150, 200],
    "co":     [2, 4, 6, 8],
    "so2":    [20, 40, 60, 100],
}

def compute_sub_index_rs(value: float, breakpoints: list) -> int:
    """Return sub-index (1-5) for a pollutant value based on RS breakpoints."""
    for i, bp in enumerate(breakpoints):
        if value <= bp:
            return i + 1
    return 5

def compute_overall_aqi_rs(data: dict) -> (int, str):
    """
    Izračuna celotni AQI kot maksimum podindeksov in preslika v kategorijo.
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
                _LOGGER.warning("Neveljavna vrednost za %s: %s", pollutant, value)
    overall_index = max(sub_indices) if sub_indices else None
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
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO Weather, Air Quality, Agro and Pollen sensors."""
    _LOGGER.info("Inicializiram ARSO Weather senzorje z config_entry: %s", config_entry.data)
    entities = []

    # Naprava za globalne entitete (Pollen, Radar, Forecasts)
    global_device_info = {
        "identifiers": {(DOMAIN, "arso_weather_pollen_radar")},
        "name": "ARSO Weather Pollen and Rain Radar Station",
        "manufacturer": "ARSO",
        "model": "Pollen & Weather Sensors",
        "entry_type": "service",
    }

    entities = [
        ArsoPollenSensor(global_device_info),
        ArsoPollenForecastSensor(global_device_info)
    ]

    # Pridobimo začetne podatke za senzorje
    for entity in entities:
        await entity.async_update()

    _LOGGER.info("Adding %d sensors", len(entities))
    async_add_entities(entities, True)


    # Pridobimo lokacijo iz konfiguracije
    location = config_entry.data.get("location")
    _LOGGER.debug("Konfigurirana lokacija: %s", location)

    # Pridobimo podatke o kakovosti zraka
    air_quality_data = await fetch_air_quality_data()
    if location:
        location_normalized = normalize_location(location)
        if air_quality_data and location_normalized in air_quality_data:
            _LOGGER.info("Dodajam senzor kakovosti zraka za %s", location)
            entities.append(ArsoAirQualitySensor(hass, location, air_quality_data))
        else:
            _LOGGER.warning("⚠️ Ni podatkov o kakovosti zraka za %s", location)

    # Pridobimo agrometeorološke podatke
    agro_data = await fetch_agro_data()
    if location and agro_data:
        agro_location_norm = normalize_location(location)
        matched_station = None
        for station in AGRO_STATION_MAPPING.keys():
            if normalize_location(station) == agro_location_norm:
                matched_station = station
                break
        if matched_station:
            _LOGGER.info("Dodajam ARSO Agrometeorology senzor za %s", matched_station)
            entities.append(ArsoAgroSensor(hass, matched_station, normalize_location(matched_station), agro_data))

            entities.append(ArsoAgroSunSensor(hass, matched_station, normalize_location(matched_station), agro_data))


        else:
            _LOGGER.warning("⚠️ Lokacija %s ni podprta za agrometeorološke podatke", location)
    else:
        _LOGGER.warning("⚠️ Agrometeorološki podatki niso na voljo za %s", location)

    # Določimo spremljane vremenske parametre
    monitored_conditions = config_entry.data.get("monitored_conditions", list(SENSOR_TYPES.keys()))
    if "sun_duration" not in monitored_conditions:
        monitored_conditions.append("sun_duration")
    _LOGGER.debug("Monitored conditions: %s", monitored_conditions)
    
    if monitored_conditions:
        for sensor_type in monitored_conditions:
            _LOGGER.debug("Dodajam vremenski senzor tipa: %s", sensor_type)
            entities.append(ArsoWeatherSensor(hass, location, sensor_type, monitored_conditions))
    else:
        _LOGGER.warning("Ni določenih monitored_conditions za %s", location)

    _LOGGER.info("Skupno dodajam %d senzorjev", len(entities))
    async_add_entities(entities, True)

    global_device_info = {
        "identifiers": {(DOMAIN, "arso_weather_pollen_radar")},
        "name": "ARSO Weather Pollen and Rain Radar Station",
        "manufacturer": "ARSO",
        "model": "Pollen & Weather Cameras",
        "entry_type": "service",
    }

    # Dodamo Pollen senzor
    entities.append(ArsoPollenSensor(global_device_info))
    _LOGGER.debug("Pollen sensor added.")

    _LOGGER.info("Adding %d sensors", len(entities))
    async_add_entities(entities, True)

# ------------------------------------------------------------------
# ArsoAirQualitySensor: Senzor za AQI (RS lestvica)
# ------------------------------------------------------------------
class ArsoAirQualitySensor(Entity):
    """Reprezentacija senzorja za kakovost zraka z RS klasifikacijo AQI."""

    def __init__(self, hass, location, air_quality_data: dict):
        """Inicializacija senzorja za kakovost zraka."""
        self._hass = hass
        self._location = location
        self._state = None
        self._attributes = {}
        _LOGGER.info("Inicializiram Air Quality senzor za %s", location)
        self.update_air_quality_data(air_quality_data)

    def update_air_quality_data(self, air_quality_data: dict):
        """Posodobi podatke o kakovosti zraka in izračunaj AQI."""
        _LOGGER.debug("Prejeti podatki o kakovosti zraka: %s", air_quality_data)
        location_normalized = normalize_location(self._location)
        if not air_quality_data or location_normalized not in air_quality_data:
            _LOGGER.warning("⚠️ Ni podatkov o kakovosti zraka za %s (normalized: %s)", self._location, location_normalized)
            self._state = "Ni podatkov"
            return
        data = air_quality_data.get(location_normalized, {})
        overall_index, category = compute_overall_aqi_rs(data)
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
        _LOGGER.info("Posodobljeni Air Quality podatki za %s: %s", self._location, self._attributes)

    async def async_update(self):
        """Pridobi najnovejše podatke o kakovosti zraka."""
        _LOGGER.debug("Posodabljam Air Quality senzor za %s", self._location)
        air_quality_data = await fetch_air_quality_data()
        if air_quality_data:
            self.update_air_quality_data(air_quality_data)
        else:
            _LOGGER.warning("Air Quality podatki so prazni ali None!")

    @property
    def unique_id(self):
        return f"arso_weather_{normalize_location(self._location)}_air_quality"

    @property
    def name(self):
        return f"ARSO Weather {self._location.capitalize()} - Air Quality"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

# ------------------------------------------------------------------
# ArsoWeatherSensor: Senzor za vremenske podatke
# ------------------------------------------------------------------
class ArsoWeatherSensor(Entity):
    """Reprezentacija senzorja za vremenske podatke."""

    def __init__(self, hass, location, sensor_type, monitored_conditions: list):
        """Inicializacija vremenskega senzorja."""
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
        """Vrne edinstven ID senzorja"""
        if not self._location or not self._sensor_type:
            return None  # Poskrbimo, da ne vrača None, kar povzroči napako
        return f"arso_weather_{self._location.replace(' ', '_').lower()}_{self._sensor_type}"

    @property
    def name(self):
        """Vrne ime senzorja"""
        if not self._location or not self._sensor_type:
            return "Neznan ARSO Weather Sensor"  # Prepreči None vrednost
        return f"ARSO Weather {self._location.capitalize()} - {SENSOR_TYPES[self._sensor_type][0]}"


    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return self._attr_unit_of_measurement

    @property
    def icon(self):
        return self._icon

    @property
    def device_class(self):
        return self._device_class

    @property
    def available(self):
        return self._state is not None

    @property
    def extra_state_attributes(self):
        return {}

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    @property
    def entity_registry_enabled_default(self) -> bool:
        return True

    async def async_update(self):
        """Posodobi stanje vremenskega senzorja."""
        if self._sensor_type not in self._monitored_conditions:
            self._state = None
            return

        if self._sensor_type == "native_apparent_temperature":
            _LOGGER.info("Fetching UTCI data for apparent temperature in %s...", self._location)
            self._state = await fetch_utci_data(self._hass, self._location)
            _LOGGER.info("Apparent Temperature for %s: %s", self._location, self._state)
            return

        if self._sensor_type == "sun_duration":
            agro_sun_sensor = self._hass.states.get(f"sensor.arso_weather_{normalize_location(self._location)}_sunshine")
            if agro_sun_sensor and agro_sun_sensor.state not in [None, "unknown", "unavailable"]:
                self._state = agro_sun_sensor.state
                _LOGGER.info("✅ Sun duration for %s: %s", self._location, self._state)
            else:
                _LOGGER.warning("⚠️ Sun duration data for %s is not available in HA states!", self._location)
                self._state = None





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
                        _LOGGER.warning("Failed to fetch data for %s: HTTP %s", self._location, response.status)
                        self._state = None
                        return

                    data = await response.json()
                    forecast1h = data.get("forecast1h", {}).get("features", [])[0].get("properties", {}).get("days", [])
                    if not forecast1h:
                        _LOGGER.warning("No forecast data available for %s", self._location)
                        self._state = None
                        return

                    timeline = forecast1h[0].get("timeline", [])
                    if not timeline:
                        _LOGGER.warning("No timeline data available for %s", self._location)
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
                    _LOGGER.debug("Updated %s for %s: %s", self._sensor_type, self._location, self._state)
            except Exception as e:
                _LOGGER.error("Error fetching data for %s: %s", self._location, e)
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
                        _LOGGER.debug("Updated attribute %s for %s: %s", self._sensor_type, self._location, self._state)
                    else:
                        self._state = None
                        _LOGGER.warning("Attribute '%s' not found in weather entity for %s", self._sensor_type, self._location)
                    return
                _LOGGER.debug("Weather entity not found for %s. Retrying...", formatted_location)
                await sleep(2)
            _LOGGER.warning("Weather entity for %s not found after retries.", formatted_location)
            self._state = None

# ------------------------------------------------------------------
# ArsoPollenSensor: Senzor za cvetni prah
# ------------------------------------------------------------------
class ArsoPollenSensor(Entity):
    """Representation of the ARSO Pollen sensor."""

    def __init__(self, device_info):
        """Initialize the sensor."""
        self._state = None
        self._attributes = {}
        self._device_info = device_info
        _LOGGER.info("Initialized ARSO Pollen sensor.")

    async def async_update(self):
        """Fetch the latest pollen data."""
        _LOGGER.debug("Updating ARSO Pollen sensor...")
        data = await fetch_pollen_data()
        if data:
            # Preoblikujemo state: seznam imen rastlin z malo začetnico
            plant_names = [rastlina["ime"].lower() for rastlina in data]
            self._state = ", ".join(plant_names) if plant_names else "Ni podatkov"

            # Atribute preoblikujemo v bolj berljivo obliko
            self._attributes = {
                rastlina["ime"].lower(): {
                    "id": rastlina.get("id", "Ni podatkov"),
                    "ime": rastlina["ime"].lower(),
                    "lat": rastlina.get("ime_lat", "Ni podatkov"),
                    "faza": rastlina["faze"][0]["id_faze"] if rastlina.get("faze") else "Ni podatkov",
                    "ime_faze": rastlina["faze"][0]["ime_faze"] if rastlina.get("faze") else "Ni podatkov",
                }
                for rastlina in data
            }

            _LOGGER.info("ARSO Pollen sensor updated: %s", self._state)
        else:
            self._state = "Ni podatkov"
            self._attributes = {}
            _LOGGER.warning("No pollen data available!")

    @property
    def name(self):
        return "ARSO Pollen Sensor"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return {
            **self._attributes,
            "icon": "mdi:flower",
            "friendly_name": "ARSO Pollen Sensor"
        }

    @property
    def unique_id(self):
        return f"{DOMAIN}_pollen_{self._device_info['identifiers']}"


    @property
    def icon(self):
        return "mdi:flower"

    @property
    def device_info(self):
        return self._device_info

class ArsoPollenForecastSensor(Entity):
    """Representation of the ARSO Pollen Forecast sensor."""

    def __init__(self, device_info):
        """Initialize the forecast sensor."""
        self._state = None
        self._attributes = {}
        self._device_info = device_info
        _LOGGER.info("Initialized ARSO Pollen Forecast sensor.")

    async def async_update(self):
        """Fetch the latest pollen forecast data."""
        _LOGGER.debug("Updating ARSO Pollen Forecast sensor...")
        data = await fetch_pollen_forecast()
        if data:
            pubdate = data["articleinfo"].get("pubdate", "Ni podatkov")
            ts_updated = data.get("tsUpdated", "Ni podatkov")

            # Poiščemo napoved cvetnega prahu
            pollen_forecast_section = next(
                (section for section in data["section"] if section["title"] == "NAPOVED CVETNEGA PRAHU V ZRAKU"),
                None
            )

            pollen_forecast_text = "\n".join(pollen_forecast_section["para"]) if pollen_forecast_section else "Ni podatkov"

            self._state = "Napoved na voljo" if pollen_forecast_text else "Ni podatkov"
            self._attributes = {
                "napoved": pollen_forecast_text,
                "datum": pubdate,
                "posodobljeno": ts_updated,
                "icon": "mdi:flower-pollen",
                "friendly_name": "ARSO Pollen Forecast"
            }

            _LOGGER.info("ARSO Pollen Forecast sensor updated.")
        else:
            self._state = "Ni podatkov"
            self._attributes = {}
            _LOGGER.warning("No pollen forecast data available!")

    @property
    def name(self):
        return "ARSO Pollen Forecast"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def unique_id(self):
        return f"{DOMAIN}_pollen_forecast_{self._device_info['identifiers']}"


    @property
    def icon(self):
        return "mdi:flower-pollen"

    @property
    def device_info(self):
        return self._device_info
