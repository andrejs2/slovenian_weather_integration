"""The Slovenian Weather Integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    MODULE_AGROMETEO,
    MODULE_AIR_QUALITY,
    MODULE_AVALANCHE,
    MODULE_BIO_WEATHER,
    MODULE_UTCI,
    MODULE_MOUNTAIN,
    MODULE_PLATFORMS,
    MODULE_RADAR,
    MODULE_SKI,
    MODULE_TEXT_FORECAST,
    MODULE_WARNINGS,
    MODULE_WEBCAMS,
    ArsoConfigEntry,
    ArsoRuntimeData,
    get_enabled_modules,
)
from .coordinator import (
    CONF_WEBCAM_LOCATIONS,
    AgrometeoCoordinator,
    AirQualityCoordinator,
    ArsoDataUpdateCoordinator,
    AvalancheCoordinator,
    UtciCoordinator,
    BioWeatherCoordinator,
    MountainForecastCoordinator,
    SkiResortCoordinator,
    TextForecastCoordinator,
    WarningsCoordinator,
    WebcamCoordinator,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(
    hass: HomeAssistant, entry: ArsoConfigEntry
) -> bool:
    """Set up Slovenian Weather Integration from a config entry."""
    modules = get_enabled_modules(entry)
    _LOGGER.debug(
        "Setting up ARSO entry %s (%s). Enabled modules: %s. Options: %s",
        entry.entry_id,
        entry.data.get("location"),
        {k: v for k, v in modules.items() if v},
        dict(entry.options),
    )

    # Weather coordinator is always created
    coordinator = ArsoDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # Optional coordinators based on enabled modules
    text_forecast_coord = None
    if modules.get(MODULE_TEXT_FORECAST):
        text_forecast_coord = TextForecastCoordinator(hass, entry)
        await text_forecast_coord.async_config_entry_first_refresh()

    bio_weather_coord = None
    if modules.get(MODULE_BIO_WEATHER):
        bio_weather_coord = BioWeatherCoordinator(hass, entry)
        await bio_weather_coord.async_config_entry_first_refresh()

    mountain_coord = None
    if modules.get(MODULE_MOUNTAIN):
        mountain_coord = MountainForecastCoordinator(hass, entry)
        await mountain_coord.async_config_entry_first_refresh()

    ski_coord = None
    if modules.get(MODULE_SKI):
        ski_coord = SkiResortCoordinator(hass, entry)
        await ski_coord.async_config_entry_first_refresh()

    agrometeo_coord = None
    if modules.get(MODULE_AGROMETEO):
        agrometeo_coord = AgrometeoCoordinator(hass, entry)
        await agrometeo_coord.async_config_entry_first_refresh()

    air_quality_coord = None
    _LOGGER.debug(
        "AQ check: module_enabled=%s, aq_stations=%s",
        modules.get(MODULE_AIR_QUALITY),
        entry.options.get("aq_stations", []),
    )
    if modules.get(MODULE_AIR_QUALITY):
        air_quality_coord = AirQualityCoordinator(hass, entry)
        await air_quality_coord.async_config_entry_first_refresh()
        _LOGGER.debug(
            "AQ coordinator created. data keys: %s",
            list((air_quality_coord.data or {}).keys()),
        )

    utci_coord = None
    if modules.get(MODULE_UTCI):
        utci_coord = UtciCoordinator(hass, entry)
        await utci_coord.async_config_entry_first_refresh()

    avalanche_coord = None
    if modules.get(MODULE_AVALANCHE):
        avalanche_coord = AvalancheCoordinator(hass, entry)
        await avalanche_coord.async_config_entry_first_refresh()

    warnings_coord = None
    if modules.get(MODULE_WARNINGS):
        warnings_coord = WarningsCoordinator(hass, entry, coordinator)
        await warnings_coord.async_config_entry_first_refresh()

    webcam_coord = None
    webcam_locations = entry.options.get(CONF_WEBCAM_LOCATIONS, [])
    primary_loc = entry.data.get("location", "")
    has_extra_webcams = any(loc != primary_loc for loc in webcam_locations)
    if modules.get(MODULE_WEBCAMS) and has_extra_webcams:
        webcam_coord = WebcamCoordinator(hass, entry)
        await webcam_coord.async_config_entry_first_refresh()

    # Determine which platforms to load
    platforms: set[Platform] = set()
    for mod_name, enabled in modules.items():
        if enabled and mod_name in MODULE_PLATFORMS:
            platforms.update(MODULE_PLATFORMS[mod_name])

    platform_list = list(platforms)

    entry.runtime_data = ArsoRuntimeData(
        coordinator=coordinator,
        text_forecast_coordinator=text_forecast_coord,
        bio_weather_coordinator=bio_weather_coord,
        mountain_coordinator=mountain_coord,
        ski_coordinator=ski_coord,
        webcam_coordinator=webcam_coord,
        agrometeo_coordinator=agrometeo_coord,
        air_quality_coordinator=air_quality_coord,
        utci_coordinator=utci_coord,
        warnings_coordinator=warnings_coord,
        avalanche_coordinator=avalanche_coord,
        loaded_platforms=platform_list,
    )

    await hass.config_entries.async_forward_entry_setups(entry, platform_list)

    # Reload when options change (e.g. module toggling)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ArsoConfigEntry
) -> bool:
    """Unload ARSO Weather config entry."""
    return await hass.config_entries.async_unload_platforms(
        entry, entry.runtime_data.loaded_platforms
    )


async def _async_options_updated(
    hass: HomeAssistant, entry: ArsoConfigEntry
) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
