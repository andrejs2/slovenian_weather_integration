"""Constants for the Slovenian Weather Integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

if TYPE_CHECKING:
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    from .coordinator import ArsoDataUpdateCoordinator

DOMAIN = "slovenian_weather_integration"
DEFAULT_NAME = "ARSO Vreme"

# Webcam image base URL
WEBCAM_BASE_URL = (
    "https://meteo.arso.gov.si/uploads/probase/www/observ/webcam/"
)

# --- Module names ---
MODULE_WEATHER = "weather"
MODULE_WEBCAMS = "webcams"
MODULE_TEXT_FORECAST = "text_forecast"
MODULE_BIO_WEATHER = "bio_weather"
MODULE_MOUNTAIN = "mountain"
MODULE_SKI = "ski_resorts"
MODULE_RADAR = "radar"
MODULE_AGROMETEO = "agrometeo"
MODULE_AIR_QUALITY = "air_quality"
MODULE_UTCI = "utci"
MODULE_WARNINGS = "warnings"

# Maps modules to the HA platforms they provide
MODULE_PLATFORMS: dict[str, list[Platform]] = {
    MODULE_WEATHER: [Platform.WEATHER, Platform.SENSOR],
    MODULE_WEBCAMS: [Platform.IMAGE],
    MODULE_TEXT_FORECAST: [Platform.SENSOR],
    MODULE_BIO_WEATHER: [Platform.SENSOR],
    MODULE_MOUNTAIN: [Platform.SENSOR],
    MODULE_SKI: [Platform.SENSOR],
    MODULE_RADAR: [Platform.IMAGE],
    MODULE_AGROMETEO: [Platform.SENSOR],
    MODULE_AIR_QUALITY: [Platform.SENSOR],
    MODULE_UTCI: [Platform.SENSOR],
    MODULE_WARNINGS: [Platform.SENSOR, Platform.BINARY_SENSOR],
}

# Modules that provide national (not per-location) data.
# Only one config entry should enable each of these at a time.
GLOBAL_MODULES: set[str] = {
    MODULE_TEXT_FORECAST,
    MODULE_BIO_WEATHER,
    MODULE_MOUNTAIN,
    MODULE_SKI,
    MODULE_RADAR,
    MODULE_AGROMETEO,
    MODULE_AIR_QUALITY,
    MODULE_UTCI,
}

# Radar image URLs
RADAR_BASE_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/radar/"
RADAR_CURRENT_URL = RADAR_BASE_URL + "si0-rm.gif"
RADAR_ANIMATION_URL = RADAR_BASE_URL + "si0-rm-anim.gif"

# European weather map URLs (forecast images)
EU_WEATHER_MAP_BASE = (
    "https://meteo.arso.gov.si/uploads/probase/www/fproduct/graphic/sl/"
)
EU_WEATHER_MAP_TODAY_URL = EU_WEATHER_MAP_BASE + "fcast_weather_eu_d1.png"
EU_WEATHER_MAP_TOMORROW_URL = EU_WEATHER_MAP_BASE + "fcast_weather_eu_d2.png"

# Default modules for existing / new entries without explicit selection
DEFAULT_MODULES: dict[str, bool] = {
    MODULE_WEATHER: True,
}


@dataclass
class ArsoRuntimeData:
    """Runtime data for the ARSO Weather integration."""

    coordinator: ArsoDataUpdateCoordinator
    text_forecast_coordinator: DataUpdateCoordinator | None = None
    bio_weather_coordinator: DataUpdateCoordinator | None = None
    mountain_coordinator: DataUpdateCoordinator | None = None
    ski_coordinator: DataUpdateCoordinator | None = None
    webcam_coordinator: DataUpdateCoordinator | None = None
    agrometeo_coordinator: DataUpdateCoordinator | None = None
    air_quality_coordinator: DataUpdateCoordinator | None = None
    utci_coordinator: DataUpdateCoordinator | None = None
    warnings_coordinator: DataUpdateCoordinator | None = None
    loaded_platforms: list[Platform] = field(default_factory=list)


type ArsoConfigEntry = ConfigEntry[ArsoRuntimeData]


def get_enabled_modules(entry: ConfigEntry) -> dict[str, bool]:
    """Get enabled modules with backwards-compatible defaults.

    Existing entries without modules in options default to weather-only.
    """
    return entry.options.get("modules", DEFAULT_MODULES)
