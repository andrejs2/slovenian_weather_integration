from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN
import voluptuous as vol

# Define a configuration schema
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ARSO Weather component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up ARSO Weather from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    location = entry.data.get("location", "Ljubljana").lower().replace(" ", "_")
    hass.data[DOMAIN][entry.entry_id] = {"location": location}

    # Forward setup to weather and sensor platforms using `await`
    await hass.config_entries.async_forward_entry_setups(entry, ["weather", "sensor"])

    return True


    # Setup weather and sensor platforms
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "weather")
    )
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ARSO Weather config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "weather")
    unload_ok = unload_ok and await hass.config_entries.async_forward_entry_unload(entry, "sensor")

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
