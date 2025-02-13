from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
from .const import DOMAIN, DEFAULT_PLATFORMS
from .helpers import async_remove_sensors
from homeassistant.core import callback
from .config_flow import OptionsFlowHandler
import logging

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ARSO Weather component."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up Slovenian Weather integration from a config entry."""
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    if config_entry.entry_id in hass.data[DOMAIN]:
        _LOGGER.warning(
            "Config entry %s for %s has already been set up!",
            config_entry.title,
            DOMAIN,
        )
        return False

    hass.data[DOMAIN][config_entry.entry_id] = {}

    platforms = ["weather", "camera", "sensor"]
    try:
        await hass.config_entries.async_forward_entry_setups(config_entry, platforms)
    except Exception as e:
        _LOGGER.error(f"Failed to set up platforms for {config_entry.title}: {e}")
        return False

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ARSO Weather config entry."""
    platforms = entry.data.get("platforms", DEFAULT_PLATFORMS)
    unload_ok = True

    for platform in platforms:
        try:
            _LOGGER.debug("Unloading platform %s for entry: %s", platform, entry.entry_id)
            platform_unloaded = await hass.config_entries.async_forward_entry_unload(entry, platform)
            if not platform_unloaded:
                _LOGGER.warning("Platform %s for entry %s was not fully unloaded", platform, entry.entry_id)
            unload_ok = unload_ok and platform_unloaded
        except Exception as e:
            _LOGGER.error("Error unloading platform %s for entry %s: %s", platform, entry.entry_id, e, exc_info=True)
            unload_ok = False

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.debug("Entry unloaded successfully: %s", entry.entry_id)
    else:
        _LOGGER.warning("Entry %s not fully unloaded. Some resources may remain.", entry.entry_id)

    return unload_ok

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Update listener to reload platforms if options change."""
    platforms = entry.options.get("platforms", entry.data.get("platforms", ["sensor", "weather", "camera"]))
    current_platforms = entry.data.get("platforms", [])

    _LOGGER.debug("Update listener triggered for entry: %s", entry.entry_id)
    _LOGGER.debug("Updated platforms: %s", platforms)

    # Unload removed platforms
    for platform in current_platforms:
        if platform not in platforms:
            await hass.config_entries.async_forward_entry_unload(entry, platform)

    # Load newly added platforms
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    hass.config_entries.async_update_entry(entry, options={"platforms": platforms})

@staticmethod
@callback
def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowHandler:
    """Create the options flow."""
    return OptionsFlowHandler(config_entry)
