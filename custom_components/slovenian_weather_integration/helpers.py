import logging
from homeassistant.helpers.entity_registry import async_get
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

### UNUSED ###


async def async_remove_sensors(hass: HomeAssistant, config_entry: ConfigEntry):
    """Remove all sensors for a specific location."""
    location = config_entry.data.get("location").lower().replace(" ", "_")
    registry = async_get(hass)

    for entity_id in list(hass.states.async_entity_ids("sensor")):
        if entity_id.startswith(f"sensor.arso_weather_{location}"):
            registry.async_remove(entity_id)
            _LOGGER.info("Removed sensor: %s", entity_id)


async def async_remove_sensors(hass: HomeAssistant, config_entry: ConfigEntry):
    """Remove sensors for a specific location."""
    _LOGGER.debug("Attempting to remove sensors for entry: %s", config_entry.entry_id)
    location = config_entry.data.get("location").lower().replace(" ", "_")
    registry = async_get(hass)

    for entity_id in list(hass.states.async_entity_ids("sensor")):
        if entity_id.startswith(f"sensor.arso_weather_{location}"):
            _LOGGER.debug("Removing sensor: %s", entity_id)
            registry.async_remove(entity_id)
            _LOGGER.info("Removed sensor: %s", entity_id)
