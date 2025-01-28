from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN, DEFAULT_PLATFORMS
from .helpers import async_remove_sensors
from homeassistant.core import callback
from .config_flow import OptionsFlowHandler
import logging
from homeassistant.config_entries import ConfigEntry, OptionsFlow


_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ARSO Weather component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ARSO Weather from a config entry."""
    _LOGGER.debug("Setting up entry: %s", entry)
    _LOGGER.debug("Entry options: %s", entry.options)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    platforms = entry.options.get("platforms", entry.data.get("platforms", DEFAULT_PLATFORMS))
    _LOGGER.debug("Platforms to be loaded: %s", platforms)

    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True



async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ARSO Weather config entry."""
    platforms = entry.data.get("platforms", DEFAULT_PLATFORMS)
    unload_ok = True

    if "sensor" in platforms:
        _LOGGER.debug("Unloading sensors for entry: %s", entry.entry_id)
        await async_remove_sensors(hass, entry)

        try:
            platform_unloaded = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
            if not platform_unloaded:
                _LOGGER.warning("Sensor platform for entry %s was not fully unloaded", entry.entry_id)
            unload_ok = unload_ok and platform_unloaded
        except Exception as e:
            _LOGGER.error("Error unloading sensor platform for entry %s: %s", entry.entry_id, e, exc_info=True)
            unload_ok = False

    # Remove data from hass
    if unload_ok and not platforms:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    _LOGGER.debug("Entry unloaded: %s", entry.entry_id)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    platforms = entry.options.get("platforms", entry.data.get("platforms", []))
    current_platforms = entry.data.get("platforms", [])
    _LOGGER.debug("Update listener triggered for entry: %s", entry.entry_id)
    _LOGGER.debug("Updated platforms: %s", platforms)

    # Unload removed platforms
    for platform in current_platforms:
        if platform not in platforms:
            await hass.config_entries.async_forward_entry_unload(entry, platform)

    # Load newly added platforms
    for platform in platforms:
        if platform not in current_platforms:
            await hass.config_entries.async_forward_entry_setups(entry, [platform])

    hass.config_entries.async_update_entry(entry, options={"platforms": platforms})

@staticmethod
@callback
def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
    """Create the options flow."""
    return OptionsFlowHandler(config_entry)
