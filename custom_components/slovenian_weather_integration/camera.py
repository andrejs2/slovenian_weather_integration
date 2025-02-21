import aiohttp
import logging
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# URL-ji za ARSO slike
ARSO_RADAR_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rm-anim.gif"
ARSO_FORECAST_URL_TODAY = "https://meteo.arso.gov.si/uploads/probase/www/fproduct/graphic/sl/fcast_weather_eu_d1.png"
ARSO_FORECAST_URL_TOMORROW = "https://meteo.arso.gov.si/uploads/probase/www/fproduct/graphic/sl/fcast_weather_eu_d2.png"

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO camera entities."""
    _LOGGER.info("Initializing ARSO Camera entities")
    
    # Naprava za globalne entitete (Pollen, Radar, Forecasts)
    global_device_info = {
        "identifiers": {(DOMAIN, "arso_weather_pollen_radar")},
        "name": "ARSO Biovreme in vremenski radar",
        "manufacturer": "ARSO",
        "model": "Cvetni prah, vremenski radar in napoved v sliki",
        "entry_type": "service",
    }

    async_add_entities([
        ArsoRainRadarCamera(global_device_info), 
        ArsoForecastCamera("today", global_device_info),    
        ArsoForecastCamera("tomorrow", global_device_info) 
    ], True)

class ArsoRainRadarCamera(Camera):
    """Representation of the ARSO Rain Radar camera."""

    def __init__(self, device_info):
        """Initialize the Rain Radar camera."""
        super().__init__()
        self._attr_name = "ARSO Rain Radar"
        self._attr_entity_picture = ARSO_RADAR_URL
        self._attr_unique_id = f"{DOMAIN}_rain_radar"
        self._attr_device_info = device_info
        self._attr_icon = "mdi:radar" 

        _LOGGER.debug("Created Rain Radar Camera with unique_id: %s", self._attr_unique_id)

    @property
    def icon(self):
        return self._attr_icon

    async def async_camera_image(self):
        """Fetch new image from ARSO Radar."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(ARSO_RADAR_URL) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        _LOGGER.warning("Failed to fetch ARSO radar image. HTTP %s", response.status)
                        return None
        except Exception as e:
            _LOGGER.error("Error fetching ARSO radar image: %s", e)
            return None

    @property
    def entity_picture(self):
        return ARSO_RADAR_URL

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def device_info(self):
        return self._attr_device_info

class ArsoForecastCamera(Camera):
    """Representation of the ARSO Forecast camera."""

    def __init__(self, forecast_day: str, device_info):
        """Initialize the Forecast camera."""
        super().__init__()
        self.forecast_day = forecast_day.lower()
        self._attr_device_info = device_info

        if self.forecast_day == "tomorrow":
            self._attr_entity_picture = ARSO_FORECAST_URL_TOMORROW
            self._attr_name = "ARSO Forecast Weather Tomorrow"
            self._attr_unique_id = f"{DOMAIN}_forecast_tomorrow"
            self._attr_icon = "mdi:weather-cloudy" 
        else:
            self._attr_entity_picture = ARSO_FORECAST_URL_TODAY
            self._attr_name = "ARSO Forecast Weather Today"
            self._attr_unique_id = f"{DOMAIN}_forecast_today"
            self._attr_icon = "mdi:weather-partly-cloudy" 

        _LOGGER.debug("Created Forecast Camera '%s' with unique_id: %s", self._attr_name, self._attr_unique_id)

    @property
    def icon(self):
        return self._attr_icon 

    async def async_camera_image(self):
        """Fetch new image from ARSO Forecast."""
        url = ARSO_FORECAST_URL_TOMORROW if self.forecast_day == "tomorrow" else ARSO_FORECAST_URL_TODAY
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        _LOGGER.warning("Failed to fetch ARSO forecast image for %s. HTTP %s", self.forecast_day, response.status)
                        return None
        except Exception as e:
            _LOGGER.error("Error fetching ARSO forecast image for %s: %s", self.forecast_day, e)
            return None

    @property
    def entity_picture(self):
        return ARSO_FORECAST_URL_TOMORROW if self.forecast_day == "tomorrow" else ARSO_FORECAST_URL_TODAY

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def device_info(self):
        return self._attr_device_info
