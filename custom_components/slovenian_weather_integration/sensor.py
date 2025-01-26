import logging
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN
from asyncio import sleep

_LOGGER = logging.getLogger(__name__)

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
    "cloud_base": ["Cloud Base Height", None, "mdi:cloud-outline", None],
    "pressure_tendency": ["Pressure Tendency", None, "mdi:gauge", None],
    "cloud_coverage": ["Cloud Coverage", "%", "mdi:cloud", None],
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

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up ARSO Weather sensors."""
    location = config_entry.data.get("location").lower().replace(" ", "_")
    monitored_conditions = config_entry.data.get("monitored_conditions", list(SENSOR_TYPES.keys()))  # Privzeto spremljaj vse

    # Preveri, ali obstajajo spremljani pogoji
    if not monitored_conditions:
        _LOGGER.warning("No monitored_conditions specified for location: %s. No sensors will be added.", location)
        return  # Ne dodajaj entitet, če ni izbranih senzorjev

    # Ustvari entitete za spremljane senzorje
    entities = []
    for sensor_type in monitored_conditions:  # Uporabi samo izbrane senzorje
        entities.append(ArsoWeatherSensor(hass, location, sensor_type, monitored_conditions))

    # Dodaj entitete v Home Assistant
    async_add_entities(entities, True)


class ArsoWeatherSensor(Entity):
    """Representation of an ARSO Weather sensor."""

    def __init__(self, hass, location, sensor_type, monitored_conditions):
        self._hass = hass
        self._location = location
        self._sensor_type = sensor_type
        self._monitored_conditions = monitored_conditions  # Spremljani senzorji
        self._attr_name = f"ARSO Weather {location.capitalize()} - {SENSOR_TYPES[sensor_type][0]}"
        self._attr_unit_of_measurement = SENSOR_TYPES[sensor_type][1]
        self._icon = SENSOR_TYPES[sensor_type][2]
        self._device_class = SENSOR_TYPES[sensor_type][3]
        self._state = None

    @property
    def unique_id(self):
        """Return a unique ID for the sensor."""
        return f"arso_weather_{self._location}_{self._sensor_type}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._location.capitalize()} {SENSOR_TYPES[self._sensor_type][0]}"

    @property
    def state(self):
        """Return the state of the sensor."""
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
        """Return the device class of the sensor."""
        return self._device_class

    @property
    def device_info(self):
        """Return device information to group all related entities under one device."""
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._location.capitalize()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    async def async_update(self):
        """Fetch data for the sensor."""
        # Preveri, ali je senzor med spremljanimi
        if self._sensor_type not in self._monitored_conditions:
            self._state = None
            return

        session = async_get_clientsession(self._hass)
        api_url = f"https://vreme.arso.gov.si/api/1.0/location/?location={self._location.capitalize()}"

        # Fetch data from the API for specific sensors
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
                    timeline = data.get("forecast1h", {}).get("features", [])[0].get("properties", {}).get("days", [])[0].get("timeline", [])
                    if not timeline:
                        _LOGGER.warning("No forecast data available for %s", self._location)
                        self._state = None
                        return

                    # Pridobitev podatkov za prvo časovno točko
                    current_forecast = timeline[0]

                    if self._sensor_type == "weather_phenomenon":
                        self._state = current_forecast.get("clouds_shortText_wwsyn_shortText", None)
                    elif self._sensor_type == "condition":
                        self._state = current_forecast.get("clouds_shortText", None)
                    elif self._sensor_type == "snow_accumulation":
                        self._state = current_forecast.get("sn_acc", None)
                    elif self._sensor_type == "precipitation":
                        self._state = current_forecast.get("tp_acc", None)
                    elif self._sensor_type == "cloud_base":
                        self._state = current_forecast.get("cloudBase_shortText", None)
                    elif self._sensor_type == "pressure_tendency":
                        self._state = current_forecast.get("pa_shortText", None)
                    elif self._sensor_type == "cloud_coverage":
                        cloud_text = current_forecast.get("clouds_shortText", "jasno").lower()
                        self._state = CLOUD_COVERAGE_MAP.get(cloud_text, 0)
                    else:
                        _LOGGER.warning("Unknown sensor type: %s", self._sensor_type)
                        self._state = None

            except Exception as e:
                _LOGGER.error("Error fetching data for %s: %s", self._location, e)
                self._state = None

        else:
            # Fetch data from the weather entity for other sensors
            for _ in range(5):  # Poskusi največ 5-krat
                weather_entity = self.hass.states.get(f"weather.arso_vreme_{self._location}")
                if weather_entity:
                    attributes = weather_entity.attributes
                    if self._sensor_type in attributes:
                        self._state = attributes[self._sensor_type]
                    else:
                        self._state = None
                        _LOGGER.warning(
                            "Attribute '%s' not found in weather entity weather.arso_vreme_%s",
                            self._sensor_type,
                            self._location,
                        )
                    return
                else:
                    _LOGGER.debug("Weather entity weather.arso_vreme_%s not found. Retrying...", self._location)
                    await sleep(2)  # Počakaj 2 sekundi, preden poskusiš znova

            # Če entiteta še vedno ne obstaja po 5 poskusih
            _LOGGER.warning("Weather entity weather.arso_vreme_%s not found after retries.", self._location)
            self._state = None
