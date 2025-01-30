import aiohttp
import logging
from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

ARSO_RADAR_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/radar/si0-rrg.gif"

async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up ARSO Rain Radar camera entity."""
    async_add_entities([ArsoRainRadarCamera(config_entry.entry_id)], True)


class ArsoRainRadarCamera(Camera):
    """Representation of the ARSO Rain Radar camera."""

    def __init__(self, entry_id):
        """Initialize the camera."""
        super().__init__()
        self._attr_name = "ARSO Rain Radar"
        self._attr_entity_picture = ARSO_RADAR_URL
        self._attr_unique_id = f"{DOMAIN}_rain_radar_{entry_id}"  # ✅ Unique ID

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
