from __future__ import annotations

import importlib.util
import logging
from typing import List

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    DEFAULT_PLATFORMS,
    MOUNTAIN_COORDINATOR_KEY,
    CONF_ENABLE_MOUNTAIN,
)
from .coordinator import ArsoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SUPPORTED_PLATFORMS: List[Platform] = [Platform.SENSOR, Platform.WEATHER]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    _LOGGER.debug("async_setup for %s completed", DOMAIN)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug(
        "Setting up entry %s (title=%s) with options=%s",
        entry.entry_id, entry.title, entry.options
    )

    hass.data.setdefault(DOMAIN, {})

    # Core coordinator
    coordinator = ArsoDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    _LOGGER.debug("Core coordinator ready for %s", entry.entry_id)

    # Mountain (conditionally)
    _LOGGER.debug("Entry %s options at setup: %s", entry.entry_id, entry.options)
    if entry.options.get(CONF_ENABLE_MOUNTAIN, False):
        try:
            spec = importlib.util.find_spec(
                "custom_components.slovenian_weather_integration.coordinator_mountain"
            )
            if spec is None:
                _LOGGER.error(
                    "Mountain enabled, but coordinator_mountain.py not found at expected path"
                )
            else:
                from .coordinator_mountain import MountainDataUpdateCoordinator  # type: ignore
                mcoord = MountainDataUpdateCoordinator(hass, entry)
                await mcoord.async_config_entry_first_refresh()
                hass.data[DOMAIN][MOUNTAIN_COORDINATOR_KEY.format(entry.entry_id)] = mcoord
                _LOGGER.debug("Mountain coordinator ready for %s", entry.entry_id)
        except Exception as err:
            _LOGGER.exception("Failed to initialize Mountain coordinator: %s", err)

    # Platforms to load
    platforms = entry.options.get("platforms", DEFAULT_PLATFORMS)
    platforms_enum: list[Platform] = []
    for p in platforms:
        try:
            platforms_enum.append(Platform(p))
        except Exception:
            _LOGGER.warning("Unknown platform '%s' in options; skipping", p)
    if not platforms_enum:
        platforms_enum = SUPPORTED_PLATFORMS

    await hass.config_entries.async_forward_entry_setups(entry, platforms_enum)
    _LOGGER.info(
        "Entry %s set up with platforms=%s",
        entry.entry_id, [p.value for p in platforms_enum]
    )

    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Unloading entry %s", entry.entry_id)

    platforms = entry.options.get("platforms", DEFAULT_PLATFORMS)
    platforms_enum: list[Platform] = []
    for p in platforms:
        try:
            platforms_enum.append(Platform(p))
        except Exception:
            pass
    if not platforms_enum:
        platforms_enum = SUPPORTED_PLATFORMS

    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms_enum)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.data[DOMAIN].pop(MOUNTAIN_COORDINATOR_KEY.format(entry.entry_id), None)
        _LOGGER.info("Unloaded entry %s", entry.entry_id)
    else:
        _LOGGER.warning("Failed to unload entry %s", entry.entry_id)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    _LOGGER.debug("Options updated for %s -> reloading entry", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


@callback
def async_get_options_flow(config_entry: ConfigEntry):
    _LOGGER.debug("async_get_options_flow() called for entry %s", config_entry.entry_id)
    from .config_flow import OptionsFlowHandler  # lazy import
    return OptionsFlowHandler(config_entry)
