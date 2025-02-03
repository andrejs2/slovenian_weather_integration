import aiohttp
import logging
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# MOD: Posodobljen URL za Rain Radar (animirana slika)
ARSO_RADAR_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rm-anim.gif"

#Use this link if only last radar picture is wanted:
#https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rrg.gif

# MOD: URL za Forecast Today (d1) in Forecast Tomorrow (d2)
ARSO_FORECAST_URL_TODAY = "https://meteo.arso.gov.si/uploads/probase/www/fproduct/graphic/sl/fcast_weather_eu_d1.png"
ARSO_FORECAST_URL_TOMORROW = "https://meteo.arso.gov.si/uploads/probase/www/fproduct/graphic/sl/fcast_weather_eu_d2.png"

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO camera entities."""
    _LOGGER.info("Initializing ARSO Camera entities")
    async_add_entities([
        ArsoRainRadarCamera(), 
        ArsoForecastCamera("today"),    # Forecast for Today (d1)
        ArsoForecastCamera("tomorrow")    # Forecast for Tomorrow (d2)
    ], True)

class ArsoRainRadarCamera(Camera):
    """Representation of the ARSO Rain Radar camera."""

    def __init__(self):
        """Initialize the Rain Radar camera."""
        super().__init__()
        self._attr_name = "ARSO Rain Radar"
        self._attr_entity_picture = ARSO_RADAR_URL
        # MOD: Fiksni unikaten ID, tako da se ustvari samo ena entiteta
        self._attr_unique_id = f"{DOMAIN}_rain_radar"
        _LOGGER.debug("Created Rain Radar Camera with unique_id: %s", self._attr_unique_id)

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
        """Return the URL of the camera image."""
        return ARSO_RADAR_URL

    @property
    def unique_id(self):
        """Return the unique ID of the camera entity."""
        return self._attr_unique_id

class ArsoForecastCamera(Camera):
    """Representation of the ARSO Forecast camera."""

    def __init__(self, forecast_day: str):
        """Initialize the Forecast camera."""
        super().__init__()
        # MOD: Shrani forecast_day v lastnost
        self.forecast_day = forecast_day.lower()
        _LOGGER.debug("Initializing Forecast Camera for forecast_day: %s", self.forecast_day)
        if self.forecast_day == "tomorrow":
            self._attr_entity_picture = ARSO_FORECAST_URL_TOMORROW
            self._attr_name = "ARSO Forecast Weather Tomorrow"
            self._attr_unique_id = f"{DOMAIN}_forecast_tomorrow"
        else:
            # Default to "today"
            self._attr_entity_picture = ARSO_FORECAST_URL_TODAY
            self._attr_name = "ARSO Forecast Weather Today"
            self._attr_unique_id = f"{DOMAIN}_forecast_today"
        _LOGGER.debug("Created Forecast Camera '%s' with unique_id: %s", self._attr_name, self._attr_unique_id)

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
        """Return the URL of the forecast image."""
        return ARSO_FORECAST_URL_TOMORROW if self.forecast_day == "tomorrow" else ARSO_FORECAST_URL_TODAY

    @property
    def unique_id(self):
        """Return the unique ID of the forecast camera entity."""
        return self._attr_unique_id
