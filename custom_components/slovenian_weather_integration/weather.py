import logging
from astral.sun import sun
from astral import LocationInfo
import datetime
from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_WIND_SPEED,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_PRESSURE,
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_SUNNY,
    ATTR_FORECAST_IS_DAYTIME,
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfPrecipitationDepth,
    CONF_LOCATION,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .coordinator import ArsoDataUpdateCoordinator
from .const import DOMAIN

from .arso_weather.models import (
    ObservationDetails,
    Forecast1hTimelineEntry,
    Forecast3hTimelineEntry,
    Forecast24hTimelineEntry,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO weather entity based on a config entry."""
    coordinator: ArsoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ArsoWeatherEntity(coordinator, entry)])


class ArsoWeatherEntity(CoordinatorEntity[ArsoDataUpdateCoordinator], WeatherEntity):
    """Representation of ARSO weather data."""

    _attr_has_entity_name = True
    _attr_name = None

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_TWICE_DAILY
    )

    def __init__(
        self, coordinator: ArsoDataUpdateCoordinator, entry: ConfigEntry
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self.config_entry = entry
        self._location = entry.data.get(CONF_LOCATION, "ARSO Weather")

        self._attr_unique_id = f"{entry.entry_id}_weather"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._location)},
            name="ARSO Weather " + self._location,
            manufacturer="ARSO",
            model="Weather Station",
            entry_type="service",
        )

    # --- Helper to safely get current data (first item from list) ---
    @property
    def _current_data(self) -> ObservationDetails | None:
        """Safely get current weather data from coordinator data dictionary."""
        if self.coordinator.data and (
            current_list := self.coordinator.data.get("current")
        ):
            if current_list:
                return current_list[0]
        return None

    # --- Required properties ---
    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        return self._current_data.temperature if self._current_data else None

    @property
    def native_temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def native_precipitation_unit(self) -> str:
        return UnitOfPrecipitationDepth.MILLIMETERS

    @property
    def humidity(self) -> float | None:
        """Return the current humidity."""
        if (
            self._current_data
            and self._current_data.relative_humidity_percent is not None
        ):
            return float(self._current_data.relative_humidity_percent)
        return None

    @property
    def native_pressure(self) -> float | None:
        """Return the current sea-level pressure."""
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
        """Return the current wind speed."""
        return self._current_data.wind_speed_kmh if self._current_data else None

    @property
    def native_wind_speed_unit(self) -> str:
        return UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the current wind bearing."""
        return self._current_data.wind_direction_text if self._current_data else None

    @property
    def native_visibility(self) -> float | None:
        """Return the current visibility."""
        return (
            self._current_data.visibility_km
            if hasattr(self._current_data, "visibility_km")
            else None
        )

    @property
    def native_visibility_unit(self) -> str:
        return UnitOfLength.KILOMETERS

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        if self._current_data:
            condition = self._current_data.home_assistant_weather_condition
            return condition_to_night_time(
                condition, dt=datetime.datetime.now(datetime.UTC)
            )
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available. Requires 'current' data in coordinator."""
        # Check coordinator availability and presence of the 'current' key with data
        return (
            super().available
            and self.coordinator.data is not None
            and (current_list := self.coordinator.data.get("current")) is not None
            and bool(current_list)  # Check if list is not empty
        )

    # --- Forecast Method ---
    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast."""
        if not self.coordinator.data or not self.coordinator.data.get("forecast1h"):
            _LOGGER.debug(
                "Hourly forecast ('forecast1h') not available in coordinator data"
            )
            return None

        forecast_list: list[Forecast1hTimelineEntry] = self.coordinator.data.get(
            "forecast1h"
        )
        ha_forecast: list[Forecast] = []

        for item in forecast_list:
            if item.valid_time is None:
                continue

            forecast_entry: Forecast = {
                ATTR_FORECAST_TIME: item.valid_time.isoformat(),
                ATTR_FORECAST_TEMP: item.temperature,
                ATTR_FORECAST_PRECIPITATION: item.accumulated_precipitation_mm,
                ATTR_FORECAST_CONDITION: condition_to_night_time(
                    item.home_assistant_weather_condition, dt=item.valid_time
                ),
                ATTR_FORECAST_WIND_SPEED: item.wind_speed_kmh,
                ATTR_FORECAST_WIND_BEARING: item.wind_direction_text,
                ATTR_FORECAST_HUMIDITY: item.relative_humidity_percent,
                ATTR_FORECAST_PRESSURE: item.mean_sea_level_pressure_hpa,
                "snow_precipitation": item.accumulated_snow_mm,
            }
            ha_forecast.append(
                {k: v for k, v in forecast_entry.items() if v is not None}
            )

        return ha_forecast[:11]

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the hourly forecast."""
        if not self.coordinator.data or not self.coordinator.data.get("forecast24h"):
            _LOGGER.debug(
                "Hourly forecast ('forecast24h') not available in coordinator data"
            )
            return None

        forecast_list: list[Forecast24hTimelineEntry] = self.coordinator.data.get(
            "forecast24h"
        )
        ha_forecast: list[Forecast] = []

        for item in forecast_list:
            if item.valid_time is None:
                continue

            forecast_entry: Forecast = {
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
                {k: v for k, v in forecast_entry.items() if v is not None}
            )

        return ha_forecast[:11]

    # --- Forecast Processing Method ---
    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        """Return the twice a day forecast."""
        if not self.coordinator.data or not self.coordinator.data.get("forecast3h"):
            _LOGGER.debug(
                "3-hour forecast ('forecast3h') not available in coordinator data"
            )
            return None

        forecast_list: list[Forecast3hTimelineEntry] = self.coordinator.data.get(
            "forecast3h"
        )
        ha_forecast: list[Forecast] = []

        max_forecast_date = (
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3)
        ).date()

        for i, item in enumerate(forecast_list):
            if item.valid_time is None:
                continue
            if item.valid_time.date() > max_forecast_date:
                continue
            hour = item.valid_time.hour
            if hour not in [9, 21]:
                continue

            # take this and three items
            # for day vals, this will be hours 9, 12, 15, 18
            # for night vals, this will be hours 21, 0, 3, 6
            half_day_forecasts = forecast_list[i : i + 4]

            # this is representative forecast for the half day
            # for day this will be at 12:00
            # for night this will be at 0:00
            main_half_day_forecast = forecast_list[i + 1]

            forecast_entry: Forecast = {
                ATTR_FORECAST_IS_DAYTIME: True if hour == 9 else False,
                ATTR_FORECAST_TIME: item.valid_time.isoformat(),
                ATTR_FORECAST_TEMP: max([f.temperature for f in half_day_forecasts]),
                ATTR_FORECAST_TEMP_LOW: min(
                    [f.temperature for f in half_day_forecasts]
                ),
                ATTR_FORECAST_PRECIPITATION: sum(
                    [f.accumulated_precipitation_mm for f in half_day_forecasts]
                ),
                ATTR_FORECAST_CONDITION: condition_to_night_time(
                    main_half_day_forecast.home_assistant_weather_condition,
                    dt=main_half_day_forecast.valid_time,
                ),
                ATTR_FORECAST_WIND_SPEED: max(
                    [f.wind_speed_kmh for f in half_day_forecasts]
                ),
                ATTR_FORECAST_WIND_BEARING: main_half_day_forecast.wind_direction_text,
                ATTR_FORECAST_HUMIDITY: max(
                    [f.relative_humidity_percent for f in half_day_forecasts]
                ),
                ATTR_FORECAST_PRESSURE: max(
                    [f.mean_sea_level_pressure_hpa for f in half_day_forecasts]
                ),
                "snow_precipitation": sum(
                    [f.accumulated_snow_mm for f in half_day_forecasts]
                ),
            }
            ha_forecast.append(
                {k: v for k, v in forecast_entry.items() if v is not None}
            )

        return ha_forecast


def is_daytime(dt: datetime.datetime) -> bool:
    """Check if it is currently daytime based on the sun position."""
    loc_info = LocationInfo("Ljubljana")
    s = sun(loc_info.observer, date=dt)
    return s["sunrise"] <= dt <= s["sunset"]


def condition_to_night_time(condition: str, dt: datetime.datetime) -> str:
    """Convert condition to night time equivalent."""
    if condition == ATTR_CONDITION_SUNNY and not is_daytime(dt):
        return ATTR_CONDITION_CLEAR_NIGHT
    return condition
