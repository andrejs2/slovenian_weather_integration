"""Weather platform for the Slovenian Weather Integration."""

from __future__ import annotations

import datetime
import logging
import re

from astral import LocationInfo
from astral.sun import sun

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_SUNNY,
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_IS_DAYTIME,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_PRESSURE,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_WIND_SPEED,
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    CONF_LOCATION,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .arso_weather.models import (
    Forecast1hTimelineEntry,
    Forecast3hTimelineEntry,
    Forecast24hTimelineEntry,
    ObservationDetails,
)
from .const import DOMAIN, MODULE_AIR_QUALITY, MODULE_BIO_WEATHER, ArsoConfigEntry, get_enabled_modules
from .coordinator import ArsoDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# Default coordinates (center of Slovenia) for sun position calculation
_DEFAULT_LATITUDE = 46.15
_DEFAULT_LONGITUDE = 14.99


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArsoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO weather entity based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([ArsoWeatherEntity(coordinator, entry)])


class ArsoWeatherEntity(
    CoordinatorEntity[ArsoDataUpdateCoordinator], WeatherEntity
):
    """Representation of ARSO weather data."""

    _attr_has_entity_name = True
    _attr_name = None

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )

    def __init__(
        self,
        coordinator: ArsoDataUpdateCoordinator,
        entry: ArsoConfigEntry,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._location = entry.data.get(CONF_LOCATION, "ARSO Weather")
        self._entry = entry

        # BACKWARDS COMPAT: unique_id has NO domain prefix (asymmetry with sensors)
        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._location)},
            name="ARSO Weather " + self._location,
            manufacturer="ARSO",
            model="Vremenska postaja",
            entry_type="service",
        )

    @property
    def _current_data(self) -> ObservationDetails | None:
        """Safely get current weather data from coordinator."""
        if self.coordinator.data and (
            current_list := self.coordinator.data.get("current")
        ):
            if current_list:
                return current_list[0]
        return None

    @property
    def _location_coords(self) -> tuple[float, float]:
        """Return (latitude, longitude) for this location."""
        client = self.coordinator.client
        lat = client.latitude if client.latitude is not None else _DEFAULT_LATITUDE
        lon = client.longitude if client.longitude is not None else _DEFAULT_LONGITUDE
        return (lat, lon)

    # --- Required properties ---
    @property
    def native_temperature(self) -> float | None:
        return self._current_data.temperature if self._current_data else None

    @property
    def native_temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def native_precipitation_unit(self) -> str:
        return UnitOfPrecipitationDepth.MILLIMETERS

    @property
    def humidity(self) -> float | None:
        if self._current_data and self._current_data.relative_humidity_percent is not None:
            return float(self._current_data.relative_humidity_percent)
        return None

    @property
    def native_pressure(self) -> float | None:
        return (
            self._current_data.mean_sea_level_pressure_hpa
            if self._current_data
            else None
        )

    @property
    def native_pressure_unit(self) -> str:
        return UnitOfPressure.HPA

    @property
    def native_wind_speed(self) -> float | None:
        return self._current_data.wind_speed_kmh if self._current_data else None

    @property
    def native_wind_speed_unit(self) -> str:
        return UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def wind_bearing(self) -> float | str | None:
        return (
            self._current_data.wind_direction_text
            if self._current_data
            else None
        )

    @property
    def native_wind_gust_speed(self) -> float | None:
        if self._current_data and self._current_data.max_wind_gust_kmh is not None:
            return float(self._current_data.max_wind_gust_kmh)
        return None

    @property
    def native_dew_point(self) -> float | None:
        if self._current_data and hasattr(self._current_data, "dew_point"):
            return self._current_data.dew_point
        return None

    @property
    def native_visibility(self) -> float | None:
        if self._current_data and hasattr(self._current_data, "visibility_km"):
            return self._current_data.visibility_km
        return None

    @property
    def native_visibility_unit(self) -> str:
        return UnitOfLength.KILOMETERS

    @property
    def ozone(self) -> float | None:
        """Return ozone level from air quality coordinator if available."""
        modules = get_enabled_modules(self._entry)
        if not modules.get(MODULE_AIR_QUALITY):
            return None
        aq_coord = self._entry.runtime_data.air_quality_coordinator
        if not aq_coord or not aq_coord.data:
            return None
        # Find the nearest/first station with O3 data
        for station_data in aq_coord.data.values():
            hourly = station_data.get("hourly", {})
            o3 = hourly.get("o3")
            if o3 is not None:
                return float(o3)
        return None

    @property
    def uv_index(self) -> float | None:
        """Return UV index from bio-weather coordinator if available."""
        modules = get_enabled_modules(self._entry)
        if not modules.get(MODULE_BIO_WEATHER):
            return None
        bio_coord = self._entry.runtime_data.bio_weather_coordinator
        if not bio_coord or not bio_coord.data:
            return None
        uv_text = bio_coord.data.get("uv_index")
        if not uv_text:
            return None
        return _extract_uv_number(uv_text)

    @property
    def condition(self) -> str | None:
        if self._current_data:
            condition = self._current_data.home_assistant_weather_condition
            lat, lon = self._location_coords
            return _condition_to_night_time(
                condition,
                dt=datetime.datetime.now(datetime.UTC),
                latitude=lat,
                longitude=lon,
            )
        return None

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.data is not None
            and bool(self.coordinator.data.get("current"))
        )

    # --- Forecast Methods ---
    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast.

        Prefers 1h data (forecast1h) when available, falls back to 3h
        (forecast3h). Both share the same fields (temp, precip, wind, etc.).
        """
        if not self.coordinator.data:
            return None

        # Prefer 1h resolution, fall back to 3h
        forecast_list: list[Forecast1hTimelineEntry | Forecast3hTimelineEntry] | None = (
            self.coordinator.data.get("forecast1h")
        )
        if not forecast_list:
            forecast_list = self.coordinator.data.get("forecast3h")
        if not forecast_list:
            return None

        ha_forecast: list[Forecast] = []
        lat, lon = self._location_coords
        for item in forecast_list:
            if item.valid_time is None:
                continue
            entry: Forecast = {
                ATTR_FORECAST_TIME: item.valid_time.isoformat(),
                ATTR_FORECAST_TEMP: item.temperature,
                ATTR_FORECAST_PRECIPITATION: item.accumulated_precipitation_mm,
                ATTR_FORECAST_CONDITION: _condition_to_night_time(
                    item.home_assistant_weather_condition,
                    dt=item.valid_time,
                    latitude=lat,
                    longitude=lon,
                ),
                ATTR_FORECAST_WIND_SPEED: item.wind_speed_kmh,
                ATTR_FORECAST_WIND_BEARING: item.wind_direction_text,
                ATTR_FORECAST_HUMIDITY: item.relative_humidity_percent,
                ATTR_FORECAST_PRESSURE: item.mean_sea_level_pressure_hpa,
            }
            ha_forecast.append(
                {k: v for k, v in entry.items() if v is not None}
            )
        return ha_forecast

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        if not self.coordinator.data:
            return None
        forecast_list: list[Forecast24hTimelineEntry] | None = (
            self.coordinator.data.get("forecast24h")
        )
        if not forecast_list:
            return None

        ha_forecast: list[Forecast] = []
        for item in forecast_list:
            if item.valid_time is None:
                continue
            entry: Forecast = {
                ATTR_FORECAST_TIME: item.valid_time.isoformat(),
                ATTR_FORECAST_TEMP: item.temperature,
                ATTR_FORECAST_PRECIPITATION: item.accumulated_precipitation_24h_mm,
                ATTR_FORECAST_CONDITION: item.home_assistant_weather_condition,
                ATTR_FORECAST_WIND_SPEED: item.wind_speed_kmh,
                ATTR_FORECAST_WIND_BEARING: item.wind_direction_text,
                ATTR_FORECAST_HUMIDITY: item.relative_humidity_percent,
                ATTR_FORECAST_PRESSURE: item.mean_sea_level_pressure_hpa,
                ATTR_FORECAST_TEMP_LOW: item.min_temperature_forecast,
            }
            ha_forecast.append(
                {k: v for k, v in entry.items() if v is not None}
            )
        return ha_forecast

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """Return the twice-daily forecast (morning/evening from 3h data)."""
        if not self.coordinator.data:
            return None
        forecast_list: list[Forecast3hTimelineEntry] | None = (
            self.coordinator.data.get("forecast3h")
        )
        if not forecast_list:
            return None

        ha_forecast: list[Forecast] = []
        lat, lon = self._location_coords
        max_forecast_date = (
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=4)
        ).date()

        for i, item in enumerate(forecast_list):
            if item.valid_time is None:
                continue
            if item.valid_time.date() > max_forecast_date:
                continue
            hour = item.valid_time.hour
            if hour not in (9, 21):
                continue

            # Take this and the next 3 entries for the half-day window
            # Day (9): hours 9, 12, 15, 18
            # Night (21): hours 21, 0, 3, 6
            end_idx = min(i + 4, len(forecast_list))
            half_day = forecast_list[i:end_idx]
            if len(half_day) < 2:
                continue

            # Representative forecast is the second entry (12:00 or 00:00)
            main_forecast = half_day[1]

            temps = [f.temperature for f in half_day if f.temperature is not None]
            precips = [
                f.accumulated_precipitation_mm
                for f in half_day
                if f.accumulated_precipitation_mm is not None
            ]
            winds = [f.wind_speed_kmh for f in half_day if f.wind_speed_kmh is not None]
            humids = [
                f.relative_humidity_percent
                for f in half_day
                if f.relative_humidity_percent is not None
            ]
            pressures = [
                f.mean_sea_level_pressure_hpa
                for f in half_day
                if f.mean_sea_level_pressure_hpa is not None
            ]
            snows = [
                f.accumulated_snow_mm
                for f in half_day
                if f.accumulated_snow_mm is not None
            ]

            entry: Forecast = {
                ATTR_FORECAST_IS_DAYTIME: hour == 9,
                ATTR_FORECAST_TIME: item.valid_time.isoformat(),
            }
            if temps:
                entry[ATTR_FORECAST_TEMP] = max(temps)
                entry[ATTR_FORECAST_TEMP_LOW] = min(temps)
            if precips:
                entry[ATTR_FORECAST_PRECIPITATION] = sum(precips)
            if main_forecast.home_assistant_weather_condition:
                entry[ATTR_FORECAST_CONDITION] = _condition_to_night_time(
                    main_forecast.home_assistant_weather_condition,
                    dt=main_forecast.valid_time,
                    latitude=lat,
                    longitude=lon,
                )
            if winds:
                entry[ATTR_FORECAST_WIND_SPEED] = max(winds)
            if main_forecast.wind_direction_text:
                entry[ATTR_FORECAST_WIND_BEARING] = main_forecast.wind_direction_text
            if humids:
                entry[ATTR_FORECAST_HUMIDITY] = max(humids)
            if pressures:
                entry[ATTR_FORECAST_PRESSURE] = max(pressures)
            if snows:
                entry["snow_precipitation"] = sum(snows)

            ha_forecast.append(entry)

        return ha_forecast


def _extract_uv_number(text: str) -> float | None:
    """Extract a numeric UV index from ARSO UV text.

    ARSO UV text typically contains phrases like "UV indeks bo 3",
    "UV indeks 5-6", "UV indeks: 2" etc. Returns the first number found,
    or the average of a range.
    """
    # Look for patterns like "3-4", "5 do 6", "3"
    range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", text)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        return (low + high) / 2

    single_match = re.search(r"\b(\d+)\b", text)
    if single_match:
        return float(single_match.group(1))

    return None


def _is_daytime(
    dt: datetime.datetime,
    latitude: float = _DEFAULT_LATITUDE,
    longitude: float = _DEFAULT_LONGITUDE,
) -> bool:
    """Check if it is daytime based on sun position at given coordinates."""
    loc = LocationInfo(latitude=latitude, longitude=longitude)
    s = sun(loc.observer, date=dt)
    return s["sunrise"] <= dt <= s["sunset"]


def _condition_to_night_time(
    condition: str | None,
    dt: datetime.datetime,
    latitude: float = _DEFAULT_LATITUDE,
    longitude: float = _DEFAULT_LONGITUDE,
) -> str | None:
    """Convert 'sunny' condition to 'clear-night' when it's night."""
    if condition is None:
        return None
    if condition == ATTR_CONDITION_SUNNY and not _is_daytime(dt, latitude, longitude):
        return ATTR_CONDITION_CLEAR_NIGHT
    return condition
