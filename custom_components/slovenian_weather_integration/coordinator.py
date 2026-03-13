"""DataUpdateCoordinators for the ARSO Weather integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.const import CONF_LOCATION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .arso_weather.agrometeo_client import fetch_agrometeo_data
from .arso_weather.webcam_client import fetch_webcam_urls
from .arso_weather.avalanche_client import fetch_avalanche_data
from .arso_weather.air_quality_client import fetch_air_quality_data
from .arso_weather.utci_client import fetch_utci_data
from .arso_weather.warnings_client import (
    fetch_warnings,
    region_from_coordinates,
)
from .arso_weather.bio_weather_client import fetch_bio_weather
from .arso_weather.client import ArsoApiError, ArsoWeather
from .arso_weather.mountain_client import (
    fetch_mountain_elevation_data,
    fetch_mountain_forecast,
    fetch_mountain_forecast_json,
)
from .arso_weather.ski_client import fetch_ski_data
from .arso_weather.snow_client import fetch_snow_data, find_nearest_snow_station
from .arso_weather.text_forecast_client import fetch_text_forecast
from .const import ArsoConfigEntry

# Config option keys (must match config_flow)
CONF_MOUNTAIN_REGIONS = "mountain_regions"
CONF_WEBCAM_LOCATIONS = "webcam_locations"
CONF_AGRO_STATIONS = "agro_stations"
CONF_AQ_STATIONS = "aq_stations"
CONF_UTCI_STATIONS = "utci_stations"
CONF_AVALANCHE_REGIONS = "avalanche_regions"

# Webcam coordinator
WEBCAM_UPDATE_INTERVAL = timedelta(minutes=15)

_LOGGER = logging.getLogger(__name__)

# --- Weather coordinator (existing) ---
WEATHER_UPDATE_INTERVAL = timedelta(minutes=15)
WEATHER_REQUEST_TIMEOUT = 30

# --- Text forecast / bio-weather coordinators ---
FORECAST_UPDATE_INTERVAL = timedelta(minutes=60)
FORECAST_REQUEST_TIMEOUT = 30

# --- Mountain / ski coordinators ---
MOUNTAIN_UPDATE_INTERVAL = timedelta(minutes=60)
SKI_UPDATE_INTERVAL = timedelta(minutes=60)
SKI_REQUEST_TIMEOUT = 60  # XML is ~2 MB

# --- Agrometeo coordinator ---
AGRO_UPDATE_INTERVAL = timedelta(minutes=60)  # daily data

# --- Air quality coordinator ---
AQ_UPDATE_INTERVAL = timedelta(minutes=45)  # hourly data

# --- UTCI coordinator ---
UTCI_UPDATE_INTERVAL = timedelta(minutes=60)  # daily CSV, hourly resolution

# --- Avalanche coordinator ---
AVALANCHE_UPDATE_INTERVAL = timedelta(minutes=60)  # daily bulletin

# --- Warnings coordinator ---
WARNINGS_UPDATE_INTERVAL = timedelta(minutes=5)  # fast updates for alerts

CoordinatorDataType = dict[str, list]


class ArsoDataUpdateCoordinator(DataUpdateCoordinator[CoordinatorDataType]):
    """Manage fetching ARSO weather data (observations + forecasts)."""

    config_entry: ArsoConfigEntry
    client: ArsoWeather

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        location = entry.data[CONF_LOCATION]
        session = aiohttp_client.async_get_clientsession(hass)
        self.client = ArsoWeather(location_name=location, session=session)

        super().__init__(
            hass,
            _LOGGER,
            name=f"ARSO Vreme ({location})",
            update_interval=WEATHER_UPDATE_INTERVAL,
        )
        self.config_entry = entry

    async def _async_update_data(self) -> CoordinatorDataType:
        location = self.config_entry.data.get(CONF_LOCATION, "Unknown")
        try:
            async with asyncio.timeout(WEATHER_REQUEST_TIMEOUT):
                data = await self.client.get_weather()
        except TimeoutError as err:
            raise UpdateFailed(
                f"Timeout fetching ARSO data for {location}"
            ) from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error communicating with ARSO API for {location}: {err}"
            ) from err

        if not data or "current" not in data or not data["current"]:
            raise UpdateFailed(
                f"ARSO API returned incomplete data for {location}"
            )

        _LOGGER.debug(
            "Successfully fetched ARSO data for %s. Keys: %s",
            location,
            list(data.keys()),
        )
        return data


class TextForecastCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO text forecast (for TTS)."""

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Besedilna napoved",
            update_interval=FORECAST_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                return await fetch_text_forecast(self._session)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching text forecast") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching text forecast: {err}"
            ) from err


class BioWeatherCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO bio-weather forecast (biovreme, UV, pollen)."""

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Biovreme",
            update_interval=FORECAST_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                return await fetch_bio_weather(self._session)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching bio-weather") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching bio-weather: {err}"
            ) from err


class MountainForecastCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO mountain forecasts (text + JSON + elevation data).

    Data structure::

        {
            "today": "...",           # text forecast (HTML)
            "tomorrow": "...",        # text forecast (HTML)
            "updated": "...",         # text forecast timestamp
            "datum": "...",           # JSON: date string
            "uvod": "...",            # JSON: introduction/overview
            "zakljucek": "...",       # JSON: conclusion/recommendations
            "elevation": {            # elevation data per selected region
                "JULIAN-ALPS": { ... },
                "POHORJE": { ... },
            }
        }
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Gorska napoved",
            update_interval=MOUNTAIN_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                data = await fetch_mountain_forecast(self._session)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching mountain forecast") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching mountain forecast: {err}"
            ) from err

        # Fetch structured JSON forecast (uvod + zakljucek)
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                json_data = await fetch_mountain_forecast_json(self._session)
            data["datum"] = json_data.get("datum")
            data["uvod"] = json_data.get("uvod")
            data["zakljucek"] = json_data.get("zakljucek")
        except (TimeoutError, ArsoApiError):
            _LOGGER.warning("Failed to fetch mountain forecast JSON")

        # Fetch elevation data for selected regions
        selected_regions: list[str] = self.config_entry.options.get(
            CONF_MOUNTAIN_REGIONS, []
        )
        elevation: dict[str, dict] = {}
        for region_id in selected_regions:
            try:
                async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                    elevation[region_id] = (
                        await fetch_mountain_elevation_data(
                            self._session, region_id
                        )
                    )
            except (TimeoutError, ArsoApiError):
                _LOGGER.warning(
                    "Failed to fetch elevation data for %s", region_id
                )

        data["elevation"] = elevation
        return data


class SkiResortCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO ski resort weather data (XML)."""

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Smučišča",
            update_interval=SKI_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        try:
            async with asyncio.timeout(SKI_REQUEST_TIMEOUT):
                ski_data = await fetch_ski_data(self._session)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching ski resort data") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching ski resort data: {err}"
            ) from err

        # Enrich with snow depth from GeoJSON API
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                snow_data = await fetch_snow_data(self._session)
            _merge_snow_into_ski(ski_data, snow_data)
        except Exception:
            _LOGGER.debug("Snow data unavailable, skipping", exc_info=True)

        return ski_data


def _merge_snow_into_ski(ski_data: dict, snow_data: dict) -> None:
    """Merge snow depth measurements into ski resort data."""
    for resort_key, resort in ski_data.items():
        # Try exact name match first (case-insensitive)
        station = snow_data.get(resort_key.lower())

        # If no exact match, find nearest station by coordinates
        if station is None:
            lat = resort.get("lat")
            lon = resort.get("lon")
            if lat is not None and lon is not None:
                station = find_nearest_snow_station(
                    snow_data, lat, lon, max_distance_km=15.0
                )

        if station is not None:
            resort["snow_depth_cm"] = station.get("snow_depth_cm")
            resort["snow_new_cm"] = station.get("snow_new_cm")
            resort["snow_station"] = station.get("title")
            resort["snow_station_altitude"] = station.get("altitude")
            dist = station.get("distance_km")
            if dist is not None:
                resort["snow_station_distance_km"] = dist


class WebcamCoordinator(DataUpdateCoordinator[dict]):
    """Fetch webcam image URLs from the dedicated ARSO webcam JSON API.

    Uses per-direction JSON endpoints that always return fresh data,
    instead of observationAms which can serve stale cached responses.

    Data structure: dict keyed by location name, each value is a list
    of dicts ``[{"direction": "se", "image_url": "https://..."}]``.
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Spletne kamere",
            update_interval=WEBCAM_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        locations: list[str] = self.config_entry.options.get(
            CONF_WEBCAM_LOCATIONS, []
        )
        try:
            async with asyncio.timeout(WEATHER_REQUEST_TIMEOUT):
                return await fetch_webcam_urls(self._session, locations)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching webcam data") from err
        except Exception as err:
            raise UpdateFailed(f"Error fetching webcam data: {err}") from err


class AgrometeoCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO agrometeo data (soil temp, ETP, water balance).

    Fetches the national observation + forecast GeoJSON endpoints and
    filters to the user-selected stations.

    Data structure::

        {
            "Ljubljana": {
                "current": { "tg_5_cm": 9.9, "etp": 1.8, ... },
                "history": [...],
                "forecast": [...],
                "updated": "...",
            },
        }
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Agrometeo",
            update_interval=AGRO_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        selected: list[str] = self.config_entry.options.get(
            CONF_AGRO_STATIONS, []
        )
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                return await fetch_agrometeo_data(self._session, selected)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching agrometeo data") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching agrometeo data: {err}"
            ) from err


class AirQualityCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO air quality data (PM10, PM2.5, O3, NO2, SO2, CO).

    Fetches from www.arso.gov.si (separate server from weather data).
    Two XML endpoints: hourly measurements + daily aggregates.

    Data structure::

        {
            "Ljubljana - Bežigrad": {
                "sifra": "E22",
                "lat": 46.065, "lon": 14.512, "altitude": 299,
                "hourly": {
                    "pm10": 23.0, "pm2.5": 12.0, "o3": 45.0,
                    "no2": 18.0, "so2": 3.0, "co": 0.4,
                    "datum_od": "...", "datum_do": "...",
                },
                "daily": {
                    "pm10_dnevna": 25.0, "o3_max_8urna": 67.0,
                    "datum": "...",
                },
            },
        }
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Kakovost zraka",
            update_interval=AQ_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        selected: list[str] = self.config_entry.options.get(
            CONF_AQ_STATIONS, []
        )
        _LOGGER.debug(
            "AQ coordinator update: selected_stations=%s, all_options_keys=%s",
            selected,
            list(self.config_entry.options.keys()),
        )
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                data = await fetch_air_quality_data(self._session, selected)
            _LOGGER.debug(
                "AQ coordinator fetched %d stations: %s",
                len(data),
                list(data.keys()),
            )
            return data
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching air quality data") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching air quality data: {err}"
            ) from err


class UtciCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO UTCI (Universal Thermal Climate Index) data.

    Fetches CSV data from meteo.arso.gov.si for selected stations.
    Each station provides ~73 hourly UTCI values (~3 day forecast).

    Data structure::

        {
            "Ljubljana": {
                "url_name": "LJUBLJANA - BEZIGRAD",
                "current": {"time": "...", "utci": 12.3, "category": "..."},
                "forecast": [...],
                "min_utci": 2.1,
                "max_utci": 18.5,
            },
        }
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO UTCI",
            update_interval=UTCI_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        selected: list[str] = self.config_entry.options.get(
            CONF_UTCI_STATIONS, []
        )
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                return await fetch_utci_data(self._session, selected)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching UTCI data") from err
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching UTCI data: {err}"
            ) from err


class AvalancheCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching EAWS/CAAMLv6 avalanche bulletin data.

    Fetches daily avalanche danger ratings and problems for selected
    Slovenian alpine regions from the European Avalanche Warning Services.
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ArsoConfigEntry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Snežni plazovi",
            update_interval=AVALANCHE_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)

    async def _async_update_data(self) -> dict:
        selected: list[str] = self.config_entry.options.get(
            CONF_AVALANCHE_REGIONS, []
        )
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                return await fetch_avalanche_data(self._session, selected)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching avalanche data") from err
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching avalanche data: {err}"
            ) from err


class WarningsCoordinator(DataUpdateCoordinator[dict]):
    """Manage fetching ARSO weather warnings (ATOM feed + CAP XML).

    Auto-detects the warning region from the weather coordinator's
    location coordinates.

    Data structure::

        {
            "region": "SLOVENIA_MIDDLE",
            "region_name": "Osrednja Slovenija",
            "updated": "2026-03-12T09:09:44+01:00",
            "warnings": [
                {
                    "type": "wind",
                    "type_name": "Veter",
                    "level": 3,
                    "level_color": "oranžna",
                    "level_text": "Velika ogroženost",
                    "title": "...",
                    "description": "...",
                    "instruction": "...",
                    "onset": "...",
                    "expires": "...",
                },
            ],
        }
    """

    config_entry: ArsoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ArsoConfigEntry,
        weather_coordinator: ArsoDataUpdateCoordinator,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="ARSO Opozorila",
            update_interval=WARNINGS_UPDATE_INTERVAL,
        )
        self.config_entry = entry
        self._session = aiohttp_client.async_get_clientsession(hass)
        self._weather_coordinator = weather_coordinator
        self._region: str | None = None

    def _detect_region(self) -> str:
        """Detect warning region from weather coordinator's client coordinates."""
        if self._region:
            return self._region
        client = self._weather_coordinator.client
        lat = getattr(client, "latitude", None)
        lon = getattr(client, "longitude", None)
        if lat is not None and lon is not None:
            self._region = region_from_coordinates(lat, lon)
        else:
            self._region = "SLOVENIA_MIDDLE"
        return self._region

    async def _async_update_data(self) -> dict:
        region = self._detect_region()
        try:
            async with asyncio.timeout(FORECAST_REQUEST_TIMEOUT):
                return await fetch_warnings(self._session, region)
        except TimeoutError as err:
            raise UpdateFailed("Timeout fetching warnings") from err
        except ArsoApiError as err:
            raise UpdateFailed(
                f"Error fetching warnings: {err}"
            ) from err
