import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback # Added callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import config_validation as cv
from homeassistant.const import Platform # Ensure Platform is imported

from .const import DOMAIN, DEFAULT_PLATFORMS # DEFAULT_PLATFORMS might be used in options
from .coordinator import ArsoDataUpdateCoordinator
from .config_flow import OptionsFlowHandler # Ensure OptionsFlowHandler is imported if used for options

_LOGGER = logging.getLogger(__name__)

# Define the platforms that your integration will support.
# These were previously defined as PLATFORMS = [Platform.SENSOR, Platform.WEATHER]
# It's good practice to keep this explicit.
SUPPORTED_PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.WEATHER]

# If you had a CONFIG_SCHEMA for configuration.yaml, it would be here.
# For UI-configured integrations, this is usually minimal or just for the domain.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ARSO Weather component from YAML (not used for UI config)."""
    # This is usually a no-op for integrations configured via UI.
    # Ensure the domain data dict exists.
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("Async_setup for %s completed.", DOMAIN)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ARSO Weather from a config entry."""
    _LOGGER.debug("Setting up config entry for %s: %s", DOMAIN, entry.title)

    # Ensure the global domain data dict exists, and a sub-dict for this entry_id
    # This was slightly different in your original; standardizing it.
    hass.data.setdefault(DOMAIN, {})
    # hass.data[DOMAIN].setdefault(entry.entry_id, {}) # This line is usually not needed if coordinator is stored directly

    # Create the data update coordinator
    coordinator = ArsoDataUpdateCoordinator(hass, entry)

    # Fetch initial data so we have data when entities are set up.
    # If the refresh fails, async_config_entry_first_refresh will raise ConfigEntryNotReady.
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator in hass.data for platforms to access.
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up platforms (sensor, weather).
    # The platforms to load can be determined by options or defaults.
    # For simplicity, we'll use SUPPORTED_PLATFORMS here.
    # If you use options to enable/disable platforms, that logic would be here or in update_listener.
    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

    # Set up an options update listener.
    entry.async_on_unload(entry.add_update_listener(update_listener))

    _LOGGER.info("Successfully set up ARSO Weather for %s", entry.title)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading config entry for %s: %s", DOMAIN, entry.title)

    # Unload platforms.
    # Use SUPPORTED_PLATFORMS or determine from entry.options if dynamic.
    unload_ok = await hass.config_entries.async_forward_entry_unloads(
        entry, SUPPORTED_PLATFORMS
    )

    # Clean up hass.data if unload was successful.
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None) # Remove coordinator if it exists
        _LOGGER.info("Successfully unloaded ARSO Weather for %s", entry.title)
    else:
        _LOGGER.warning("Failed to fully unload ARSO Weather for %s", entry.title)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("Update listener called for %s options", entry.title)
    # This is where you would handle changes to options, e.g.,
    # enabling/disabling specific platforms (sensor, weather).
    # If options change, you might need to reload the entry or specific platforms.

    # Example: If platforms can be enabled/disabled via options
    # old_platforms = hass.data[DOMAIN].get(entry.entry_id, {}).get("loaded_platforms", SUPPORTED_PLATFORMS)
    # new_platforms_config = entry.options.get("platforms", DEFAULT_PLATFORMS) # Assuming options define this

    # For now, a simple reload of the entry is often sufficient if options impact setup.
    # However, more granular control (unloading/loading specific platforms) is better.
    # The original code had logic for this, which is good.

    # Based on your original code for update_listener:
    # Get the platforms that *should* be enabled based on current options.
    # DEFAULT_PLATFORMS should be defined in your const.py, e.g., ["sensor", "weather"]
    # The options flow should store the selected platforms under an "platforms" key in entry.options
    
    # Determine current "active" platforms (those that were loaded)
    # This is a bit tricky as we don't store them directly.
    # We assume SUPPORTED_PLATFORMS were attempted.
    # A more robust way is to track loaded platforms if they are truly dynamic.

    # For simplicity, if options change that require re-evaluating platforms,
    # Home Assistant often handles reloading the entry, which re-runs async_setup_entry.
    # If you have specific logic to add/remove platforms without a full reload:

    # Get currently configured platforms from options (or defaults if not set)
    # This assumes your OptionsFlowHandler saves a list of platform strings (e.g., "sensor", "weather")
    # into entry.options under a key like "enabled_platforms".
    # For this example, let's assume options are not yet used to disable platforms.
    # If they were, you'd compare new options with old and unload/load as needed.

    # If options change, it's common to just reload the integration.
    # Home Assistant will call async_unload_entry and then async_setup_entry.
    # To trigger this:
    # await hass.config_entries.async_reload(entry.entry_id)
    # However, this is usually done by HA itself when options flow finishes with an update.

    # The provided update_listener from your original code is more advanced,
    # attempting to unload/load specific platforms. Let's refine that slightly.

    # Get the set of platforms that should be active based on current options.
    # Assuming options store a list of platform strings like ["sensor", "weather"].
    # If no options are set, use DEFAULT_PLATFORMS.
    desired_platforms_str = entry.options.get("platforms", DEFAULT_PLATFORMS)
    desired_platforms_enum = {Platform(p_str) for p_str in desired_platforms_str if p_str in [pf.value for pf in SUPPORTED_PLATFORMS]}


    # Get the platforms that are currently loaded (or were attempted to be loaded).
    # This is a simplification; a more robust system might store currently loaded platforms.
    # For now, we assume all SUPPORTED_PLATFORMS were initially targeted.
    # We need to determine which ones to unload and which new ones to load.

    # Unload platforms that are in SUPPORTED_PLATFORMS but not in desired_platforms_enum
    platforms_to_unload = [p for p in SUPPORTED_PLATFORMS if p not in desired_platforms_enum]
    if platforms_to_unload:
        _LOGGER.debug(f"Unloading platforms due to option change: {platforms_to_unload} for {entry.title}")
        await hass.config_entries.async_forward_entry_unloads(entry, platforms_to_unload)

    # Load platforms that are in desired_platforms_enum but perhaps weren't loaded before
    # (or if they were unloaded and now need to be reloaded).
    # This typically means setting them up again.
    # A simple way is to just re-forward setup for all desired platforms.
    # Home Assistant's async_forward_entry_setups is idempotent for already set up platforms.
    _LOGGER.debug(f"Ensuring desired platforms are loaded: {desired_platforms_enum} for {entry.title}")
    await hass.config_entries.async_forward_entry_setups(entry, list(desired_platforms_enum))

    # It's important that the options flow correctly stores the list of enabled platform strings.
    # For example, if options are {"enable_sensor": True, "enable_weather": False},
    # the OptionsFlowHandler should translate this into entry.options = {"platforms": ["sensor"]}


# If you have an options flow, it needs to be registered
# This was in your original __init__.py
# @callback
# def async_get_options_flow(entry: ConfigEntry) -> OptionsFlowHandler: # Corrected signature
#     """Get the options flow for this handler."""
#     return OptionsFlowHandler(entry)
# However, the standard way to enable options flow is by setting `config_flow = True`
# in manifest.json and then HA will call the OptionsFlowHandler defined in config_flow.py
# The `async_get_options_flow` is usually not needed in `__init__.py` if `ConfigFlow`
# itself handles options via `async_show_form(step_id="init", handler=OptionsFlowHandler)`
# or if the OptionsFlow class is directly associated with the ConfigFlow.
# Your `config_flow.py` already defines `async_get_options_flow` at the module level, which is correct.
# So, this function is not strictly needed here in __init__.py.
