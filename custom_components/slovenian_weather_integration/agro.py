import aiohttp
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, LOCATIONS_URL
from .helpers import normalize_location

_LOGGER = logging.getLogger(__name__)

ARSO_AGRO_URL = "https://meteo.arso.gov.si/uploads/probase/www/agromet/json/sl/forecastKlima_si-agro.json"

# Preslikava merilnih postaj na Home Assistant lokacije
AGRO_STATION_MAPPING = {
    "Ljubljana": "Ljubljana",
    "Celje": "Celje",
    "Bilje pri Novi Gorici": "Bilje pri Novi Gorici",
    "Bovec": "Bovec",
    "Novo mesto": "Novo mesto",
    "Murska Sobota": "Murska Sobota",
    "Črnomelj": "Črnomelj",
    "Kočevje": "Kočevje",
    "Letališče Cerklje ob Krki": "Letališče Cerklje ob Krki",
    "Letališče Edvarda Rusjana Maribor": "Letališče Edvarda Rusjana Maribor",
    "Letališče Jožeta Pučnika Ljubljana": "Letališče Jožeta Pučnika Ljubljana",
    "Letališče Portorož": "Letališče Portorož",
    "Postojna": "Postojna",
    "Rateče": "Rateče",
    "Šmartno pri Slovenj Gradcu": "Šmartno pri Slovenj Gradcu",
}

async def fetch_agro_data():
    """Fetch agrometeorological data from ARSO."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(ARSO_AGRO_URL) as response:
                if response.status != 200:
                    _LOGGER.error("Failed to fetch ARSO Agro data: HTTP %s", response.status)
                    return None
                return await response.json()
        except Exception as e:
            _LOGGER.error("Exception fetching ARSO Agro data: %s", e)
            return None

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO agrometeorological sensors."""
    location = config_entry.data.get("location")
    if not location:
        _LOGGER.error("No location specified in the config entry!")
        return

    location_normalized = normalize_location(location)
    agro_data = await fetch_agro_data()
    if agro_data:
        async_add_entities([
            ArsoAgroSensor(hass, location, location_normalized, agro_data),
            ArsoAgroSunSensor(hass, location, location_normalized, agro_data)
        ], True)

class ArsoAgroSensor(Entity):
    """Representation of an ARSO Agrometeorology sensor."""
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._original_location}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    def __init__(self, hass, location, location_normalized, agro_data):
        """Initialize the sensor."""
        self._hass = hass
        self._original_location = location
        self._location = location_normalized
        self._state = "unknown"
        self._attributes = {}
        self._update_agro_data(agro_data)

    async def async_update(self):
        """Fetch latest data."""
        _LOGGER.debug("Updating ARSO Agro data for %s", self._original_location)
        agro_data = await fetch_agro_data()
        if agro_data:
            self._update_agro_data(agro_data)

    def _update_agro_data(self, agro_data):
        """Update sensor attributes with the latest agrometeorology data."""
        for location_entry in agro_data.get("features", []):
            location_title = normalize_location(location_entry["properties"].get("title", ""))
            if location_title == self._location:
                _LOGGER.debug("Found data for location: %s", self._original_location)
                days = location_entry["properties"].get("days", [])
                if not days:
                    _LOGGER.warning("No daily data for location %s", self._location)
                    return

                forecast = []
                for day in days:
                    timeline = day.get("timeline", [])
                    if timeline:
                        entry = timeline[0]
                        forecast_entry = {
                            "Evapotranspiration (mm)": entry.get("etp", "No Data"),
                            "Avg Temperature (°C)": entry.get("tklim", "No Data"),
                            "Min Temperature (°C)": entry.get("tn", "No Data"),
                            "Max Temperature (°C)": entry.get("tx", "No Data"),
                            "Temperature Humidity Index": entry.get("thi", "No Data"),
                            "Precipitation (mm)": entry.get("tp_24h_acc", "No Data"),
                            "Sun Duration (h)": entry.get("sunDur", "No Data"),
                            "Water Balance (mm)": entry.get("wBal", "No Data"),
                            "Date": day.get("date", "No Data")
                        }
                        forecast.append(forecast_entry)
                
                if forecast:
                    self._state = f"{forecast[0].get('Sun Duration (h)', 'No Data')}"
                    self._attributes = {"forecast": forecast, "Source": "Agencija RS za okolje"}

    @property
    def name(self):
        return f"ARSO Weather {self._original_location} - Agro Forecast"

    @property
    def unique_id(self):
        return f"arso_weather_{self._location}_agro"

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        return "h"

    @property
    def extra_state_attributes(self):
        return self._attributes


class ArsoAgroSunSensor(ArsoAgroSensor):
    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._location)},
            "name": f"ARSO Weather Station - {self._original_location}",
            "manufacturer": "ARSO",
            "model": "Weather Sensors",
            "entry_type": "service",
        }

    @property
    def unit_of_measurement(self):
        return "h"
    """Representation of an ARSO Agro Sunshine sensor."""

    def _update_sun_data(self, agro_data):
        """Extract sunshine forecast data."""
        forecast_sunshine = []
        for location_entry in agro_data.get("features", []):
            location_title = normalize_location(location_entry["properties"].get("title", ""))
            if location_title == self._location:
                days = location_entry["properties"].get("days", [])
                for day in days:
                    timeline = day.get("timeline", [])
                    if timeline:
                        entry = timeline[0]
                        forecast_sunshine.append({
                            "Sun Duration (h)": entry.get("sunDur", "No Data"),
                            "Date": day.get("date", "No Data")
                        })
                self._state = f"{forecast_sunshine[0].get('Sun Duration (h)', 'No Data')}" if forecast_sunshine else "unknown"
                self._attributes = {"forecast_sunshine": forecast_sunshine}

    async def async_update(self):
        """Fetch latest sunshine data."""
        agro_data = await fetch_agro_data()
        if agro_data:
            self._update_sun_data(agro_data)

    @property
    def name(self):
        return f"ARSO Weather {self._original_location} - Sunshine"

    @property
    def unique_id(self):
        return f"arso_weather_{self._location}_sun"

    @property
    def state(self):
        return self._state



    @property
    def extra_state_attributes(self):
        return self._attributes
