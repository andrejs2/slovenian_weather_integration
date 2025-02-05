import logging
from homeassistant.helpers.entity_registry import async_get
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

async def async_remove_sensors(hass: HomeAssistant, config_entry: ConfigEntry):
    """Remove all sensors for a specific location."""
    location = config_entry.data.get("location").lower().replace(" ", "_")
    registry = async_get(hass)

    for entity_id in list(hass.states.async_entity_ids("sensor")):
        if entity_id.startswith(f"sensor.arso_weather_{location}"):
            registry.async_remove(entity_id)
            _LOGGER.info("Removed sensor: %s", entity_id)

def normalize_location(location: str) -> str:
    """Normalizacija lokacij za skladnost z Home Assistant."""
    return (
        location.lower()
        .replace("č", "c")
        .replace("š", "s")
        .replace("ž", "z")
        .replace(" ", "_")
    )
