import logging
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get
from .const import DOMAIN
from asyncio import sleep
from .helpers import async_remove_sensors
from urllib.parse import quote
from .sun import fetch_sunshine_hours
from .utci import async_setup_entry as setup_utci_sensor
from .utci import fetch_utci_data



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

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up ARSO Weather sensors."""
    location = config_entry.data.get("location")

    monitored_conditions = config_entry.data.get("monitored_conditions", list(SENSOR_TYPES.keys())) 

    # 🆕 Ensure sunshine_hours is always included in monitored conditions
    if "sunshine_hours" not in monitored_conditions:
        monitored_conditions.append("sunshine_hours")
        
    if not monitored_conditions:
        _LOGGER.warning("No monitored_conditions specified for location: %s. No sensors will be added.", location)
        return 

    entities = []
    for sensor_type in monitored_conditions: 
        entities.append(ArsoWeatherSensor(hass, location, sensor_type, monitored_conditions))

    # 🆕 Dodaj async klic za UTCI senzor
    await setup_utci_sensor(hass, config_entry, async_add_entities)

    async_add_entities(entities, True)


class ArsoWeatherSensor(Entity):
    """Representation of an ARSO Weather sensor."""
    def __init__(self, hass, location, sensor_type, monitored_conditions):
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
        return f"arso_weather_{self._location}_{self._sensor_type}"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._location} {SENSOR_TYPES[self._sensor_type][0]}"

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
            "name": f"ARSO Weather Station - {self._location.title()}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }


    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return whether the sensor should be enabled by default."""
        enabled_by_default = ["temperature", "condition", "weather_phenomenon"]
        return self._sensor_type in enabled_by_default 
#zadnja
    async def async_update(self):
        """Fetch data for the sensor."""
        if self._sensor_type not in self._monitored_conditions:
            self._state = None
            return
        if self._sensor_type == "native_apparent_temperature":
            _LOGGER.info("Fetching UTCI data for apparent temperature...")
            self._state = await fetch_utci_data(self._hass, self._location)
            _LOGGER.info("Apparent Temperature: %s", self._state)
            return

        # Preverimo, ali je tip senzorja "sunshine_hours", in če je, pridobimo podatek posebej
        if self._sensor_type == "sunshine_hours":
            _LOGGER.info("🔆 Calling fetch_sunshine_hours()...")
            self._state = await fetch_sunshine_hours()
            _LOGGER.info("Sunshine hours fetched: %s", self._state)
            return

        session = async_get_clientsession(self._hass)

        # Kodiranje lokacije za API klic
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
                        _LOGGER.warning(
                            "Failed to fetch data for %s: HTTP %s", self._location, response.status
                        )
                        self._state = None
                        return

                    data = await response.json()
                    forecast1h = data.get("forecast1h", {}).get("features", [])[0].get("properties", {}).get("days", [])
                    if not forecast1h:
                        _LOGGER.warning("No forecast data available for %s", self._location)
                        self._state = None
                        return

                    # Pridobi podatke za prvi dan
                    first_day = forecast1h[0]
                    timeline = first_day.get("timeline", [])
                    if not timeline:
                        _LOGGER.warning("No timeline data available for %s", self._location)
                        self._state = None
                        return

                    current_forecast = timeline[0]

                    # Posodobi stanje glede na tip senzorja
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
            # Formatiranje lokacije za entiteto v Home Assistant
            formatted_location = self._location.lower()
            formatted_location = formatted_location.replace(" ", "_")
            formatted_location = formatted_location.replace("č", "c").replace("š", "s").replace("ž", "z")
            formatted_location = formatted_location.replace("ć", "c")
            formatted_location = formatted_location.replace("-", "_") 

            for _ in range(5): 
                weather_entity = self.hass.states.get(f"weather.arso_vreme_{formatted_location}")

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
                    _LOGGER.debug(
                        "Weather entity weather.arso_vreme_%s not found. Retrying...", formatted_location
                    )
                    await sleep(2)

            _LOGGER.warning(
                "Weather entity weather.arso_vreme_%s not found after retries.", formatted_location
            )
            self._state = None
