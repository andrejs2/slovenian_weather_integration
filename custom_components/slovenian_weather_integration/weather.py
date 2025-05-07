import logging
from astral import LocationInfo
from astral.sun import sun
import datetime
from typing import Any, cast, Optional, Dict, Union # Added Union

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_NATIVE_TEMP_LOW,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_HUMIDITY,
    ATTR_FORECAST_NATIVE_PRESSURE,
    ATTR_FORECAST_TIME,
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
import homeassistant.util.dt as dt_util

from .coordinator import ArsoDataUpdateCoordinator, CoordinatorDataType
from .const import DOMAIN

from .arso_weather.models import (
    ObservationDetails,
    Forecast1hTimelineEntry,
    Forecast3hTimelineEntry,
    Forecast24hTimelineEntry,
)

_LOGGER = logging.getLogger(__name__)

UV_INDEX_TEXT_MAP = {
    (0, 3): "Low",
    (3, 6): "Moderate",
    (6, 8): "High",
    (8, 11): "Very High",
    (11, float('inf')): "Extreme",
}

def get_uv_text(uv_index: Optional[float]) -> Optional[str]:
    if uv_index is None:
        return None
    for (lower, upper), text in UV_INDEX_TEXT_MAP.items():
        if lower <= uv_index < upper: # type: ignore
            return text
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO weather entity based on a config entry."""
    coordinator: ArsoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ArsoWeatherEntity(coordinator, entry)])


class ArsoWeatherEntity(CoordinatorEntity[ArsoDataUpdateCoordinator], WeatherEntity):
    """Representation of ARSO weather data, including UV index."""

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
        self._location_name = entry.data.get(CONF_LOCATION, "ARSO Weather")

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_weather"
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._location_name)},
            name=f"ARSO Weather {self._location_name}",
            manufacturer="ARSO & Temis.nl",
            model="Weather Integration",
            entry_type="service",
        )

    @property
    def _current_data(self) -> Optional[ObservationDetails]:
        """Safely get current weather data (ObservationDetails model) from coordinator."""
        if self.coordinator.data and isinstance(self.coordinator.data.get("current"), list):
            current_list = self.coordinator.data["current"]
            if current_list and isinstance(current_list[0], ObservationDetails):
                return current_list[0]
        _LOGGER.debug("Current ObservationDetails data not available in coordinator for %s", self._location_name)
        return None

    @property
    def native_temperature(self) -> Optional[float]:
        return self._current_data.temperature if self._current_data else None

    @property
    def native_temperature_unit(self) -> str:
        return UnitOfTemperature.CELSIUS

    @property
    def native_apparent_temperature(self) -> Optional[float]:
        return None

    @property
    def native_pressure(self) -> Optional[float]:
        return self._current_data.mean_sea_level_pressure_hpa if self._current_data else None

    @property
    def native_pressure_unit(self) -> str:
        return UnitOfPressure.HPA

    @property
    def humidity(self) -> Optional[float]:
        if self._current_data and self._current_data.relative_humidity_percent is not None:
            return float(self._current_data.relative_humidity_percent)
        return None

    @property
    def native_wind_speed(self) -> Optional[float]:
        return self._current_data.wind_speed_kmh if self._current_data else None

    @property
    def native_wind_speed_unit(self) -> str:
        return UnitOfSpeed.KILOMETERS_PER_HOUR

    @property
    def native_wind_gust_speed(self) -> Optional[float]:
        return self._current_data.max_wind_gust_kmh if self._current_data else None

    @property
    def wind_bearing(self) -> Optional[Union[float, str]]: # Union was missing import
        if self._current_data and self._current_data.wind_direction_degrees is not None:
            return float(self._current_data.wind_direction_degrees)
        if self._current_data and self._current_data.wind_direction_text is not None:
            return self._current_data.wind_direction_text
        return None

    @property
    def native_dew_point(self) -> Optional[float]:
        return self._current_data.dew_point if self._current_data else None

    @property
    def native_visibility(self) -> Optional[float]:
        if self._current_data and hasattr(self._current_data, "visibility_km") and self._current_data.visibility_km is not None:
            return float(self._current_data.visibility_km)
        return None

    @property
    def native_visibility_unit(self) -> str:
        return UnitOfLength.KILOMETERS

    @property
    def cloud_coverage(self) -> Optional[float]:
        return None

    @property
    def condition(self) -> Optional[str]:
        if self._current_data and self._current_data.home_assistant_weather_condition:
            valid_time = self._current_data.valid_time or dt_util.utcnow()
            return condition_to_night_time(
                self._current_data.home_assistant_weather_condition,
                dt=valid_time 
            )
        return None
    
    @property
    def ozone(self) -> Optional[float]:
        return None

    @property
    def attribution(self) -> str:
        return "Vreme: ARSO; UV Indeks: Temis.nl"

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        attrs: Dict[str, Any] = {}
        if self._current_data:
            if hasattr(self._current_data, 'current_uv_index') and self._current_data.current_uv_index is not None:
                attrs["current_uv_index"] = self._current_data.current_uv_index
                attrs["current_uv_index_text"] = get_uv_text(self._current_data.current_uv_index)

            if self._current_data.snow_depth_cm is not None:
                attrs["snow_depth_cm"] = self._current_data.snow_depth_cm
            if self._current_data.station_pressure_hpa is not None:
                attrs["station_pressure_hpa"] = self._current_data.station_pressure_hpa
            if self._current_data.precipitation_rate is not None:
                 attrs["precipitation_rate_mmh"] = self._current_data.precipitation_rate

            if self._current_data.valid_time:
                attrs["observation_time_local"] = dt_util.as_local(self._current_data.valid_time).isoformat()

        return attrs if attrs else None

    @property
    def available(self) -> bool:
        return super().available and self._current_data is not None

    async def async_forecast_hourly(self) -> Optional[list[Forecast]]:
        if not self.coordinator.data or not (hourly_data := self.coordinator.data.get("forecast1h")):
            _LOGGER.debug("Hourly forecast ('forecast1h') not available in coordinator data for %s", self._location_name)
            return None

        ha_forecast: list[Forecast] = []
        for item_model in hourly_data: # type: ignore
            if not isinstance(item_model, Forecast1hTimelineEntry) or item_model.valid_time is None:
                continue

            forecast_entry: Forecast = {
                ATTR_FORECAST_TIME: item_model.valid_time.isoformat(),
                ATTR_FORECAST_NATIVE_TEMP: item_model.temperature,
                ATTR_FORECAST_NATIVE_PRECIPITATION: item_model.accumulated_precipitation_mm,
                ATTR_FORECAST_CONDITION: condition_to_night_time(
                    item_model.home_assistant_weather_condition, dt=item_model.valid_time
                ),
                ATTR_FORECAST_NATIVE_WIND_SPEED: item_model.wind_speed_kmh,
                ATTR_FORECAST_WIND_BEARING: item_model.wind_direction_text, 
                ATTR_FORECAST_HUMIDITY: item_model.relative_humidity_percent,
                ATTR_FORECAST_NATIVE_PRESSURE: item_model.mean_sea_level_pressure_hpa,
            }
            if item_model.accumulated_snow_mm is not None:
                 forecast_entry["snow_precipitation_mm"] = item_model.accumulated_snow_mm

            ha_forecast.append({k: v for k, v in forecast_entry.items() if v is not None}) # type: ignore
        return ha_forecast

    async def async_forecast_daily(self) -> Optional[list[Forecast]]:
        if not self.coordinator.data or not (daily_data := self.coordinator.data.get("forecast24h")):
            _LOGGER.debug("Daily forecast ('forecast24h') not available in coordinator data for %s", self._location_name)
            return None

        ha_forecast: list[Forecast] = []
        for item_model in daily_data: # type: ignore
            if not isinstance(item_model, Forecast24hTimelineEntry) or item_model.valid_time is None:
                continue

            forecast_entry: Forecast = {
                ATTR_FORECAST_TIME: item_model.valid_time.isoformat(),
                ATTR_FORECAST_NATIVE_TEMP: item_model.temperature, 
                ATTR_FORECAST_NATIVE_TEMP_LOW: item_model.min_temperature_forecast,
                ATTR_FORECAST_NATIVE_PRECIPITATION: item_model.accumulated_precipitation_24h_mm,
                ATTR_FORECAST_CONDITION: condition_to_night_time( 
                    item_model.home_assistant_weather_condition, dt=item_model.valid_time
                ),
                ATTR_FORECAST_NATIVE_WIND_SPEED: item_model.wind_speed_kmh,
                ATTR_FORECAST_WIND_BEARING: item_model.wind_direction_text,
                ATTR_FORECAST_HUMIDITY: item_model.relative_humidity_percent,
                ATTR_FORECAST_NATIVE_PRESSURE: item_model.mean_sea_level_pressure_hpa,
            }
            
            if hasattr(item_model, 'uv_index') and item_model.uv_index is not None:
                forecast_entry["uv_index"] = item_model.uv_index 
                forecast_entry["uv_index_text"] = get_uv_text(item_model.uv_index)

            ha_forecast.append({k: v for k, v in forecast_entry.items() if v is not None}) # type: ignore
        return ha_forecast

    async def async_forecast_twice_daily(self) -> Optional[list[Forecast]]:
        if not self.coordinator.data or not (forecast3h_data := self.coordinator.data.get("forecast3h")):
            _LOGGER.debug("Twice daily forecast source ('forecast3h') not available for %s", self._location_name)
            return None
        
        ha_forecast: list[Forecast] = []
        
        all_3h_entries: list[Forecast3hTimelineEntry] = []
        if isinstance(forecast3h_data, list):
            for item in forecast3h_data:
                if isinstance(item, Forecast3hTimelineEntry):
                    all_3h_entries.append(item)
        
        if not all_3h_entries:
            return None

        daily_grouped_entries: Dict[datetime.date, list[Forecast3hTimelineEntry]] = {}
        for entry_model in all_3h_entries:
            if entry_model.valid_time:
                entry_date = dt_util.as_local(entry_model.valid_time).date()
                if entry_date not in daily_grouped_entries:
                    daily_grouped_entries[entry_date] = []
                daily_grouped_entries[entry_date].append(entry_model)

        max_forecast_days = 5
        days_processed = 0
        sorted_dates = sorted(daily_grouped_entries.keys())

        for day_date_local in sorted_dates:
            if days_processed >= max_forecast_days:
                break

            day_entries = daily_grouped_entries[day_date_local]
            day_period_entries: list[Forecast3hTimelineEntry] = []
            night_period_entries: list[Forecast3hTimelineEntry] = []

            for entry_model in day_entries:
                entry_hour_local = dt_util.as_local(cast(datetime.datetime, entry_model.valid_time)).hour
                if 6 <= entry_hour_local < 18:
                    day_period_entries.append(entry_model)
                else: 
                    night_period_entries.append(entry_model)
            
            if day_period_entries:
                rep_day_entry = day_period_entries[len(day_period_entries) // 2] 
                day_forecast_item: Forecast = {
                    ATTR_FORECAST_TIME: dt_util.start_of_local_day(day_date_local).replace(hour=12, tzinfo=dt_util.get_default_time_zone()).isoformat(), 
                    ATTR_FORECAST_IS_DAYTIME: True,
                    ATTR_FORECAST_CONDITION: condition_to_night_time(rep_day_entry.home_assistant_weather_condition, cast(datetime.datetime, rep_day_entry.valid_time)),
                    ATTR_FORECAST_NATIVE_TEMP: max(e.temperature for e in day_period_entries if e.temperature is not None) if any(e.temperature is not None for e in day_period_entries) else None, # type: ignore
                    ATTR_FORECAST_NATIVE_TEMP_LOW: min(e.temperature for e in day_period_entries if e.temperature is not None) if any(e.temperature is not None for e in day_period_entries) else None, # type: ignore
                    ATTR_FORECAST_NATIVE_PRECIPITATION: sum(e.accumulated_precipitation_mm for e in day_period_entries if e.accumulated_precipitation_mm is not None) if any(e.accumulated_precipitation_mm is not None for e in day_period_entries) else None, # type: ignore
                }
                ha_forecast.append({k: v for k, v in day_forecast_item.items() if v is not None}) # type: ignore

            if night_period_entries:
                rep_night_entry = night_period_entries[len(night_period_entries) // 2]
                night_forecast_item: Forecast = {
                    ATTR_FORECAST_TIME: dt_util.start_of_local_day(day_date_local).replace(hour=23, minute=59, tzinfo=dt_util.get_default_time_zone()).isoformat(), 
                    ATTR_FORECAST_IS_DAYTIME: False,
                    ATTR_FORECAST_CONDITION: condition_to_night_time(rep_night_entry.home_assistant_weather_condition, cast(datetime.datetime, rep_night_entry.valid_time)),
                    ATTR_FORECAST_NATIVE_TEMP: max(e.temperature for e in night_period_entries if e.temperature is not None) if any(e.temperature is not None for e in night_period_entries) else None, # type: ignore
                    ATTR_FORECAST_NATIVE_TEMP_LOW: min(e.temperature for e in night_period_entries if e.temperature is not None) if any(e.temperature is not None for e in night_period_entries) else None, # type: ignore
                    ATTR_FORECAST_NATIVE_PRECIPITATION: sum(e.accumulated_precipitation_mm for e in night_period_entries if e.accumulated_precipitation_mm is not None) if any(e.accumulated_precipitation_mm is not None for e in night_period_entries) else None, # type: ignore
                }
                ha_forecast.append({k: v for k, v in night_forecast_item.items() if v is not None}) # type: ignore
            
            days_processed +=1

        return ha_forecast if ha_forecast else None

def is_daytime(dt_object: datetime.datetime, latitude: float, longitude: float) -> bool:
    if dt_object.tzinfo is None:
        dt_object = dt_object.replace(tzinfo=dt_util.UTC) 
    else:
        dt_object = dt_object.astimezone(dt_util.UTC)
    try:
        city = LocationInfo("UserLocation", "UserRegion", dt_object.tzname(), latitude, longitude) # type: ignore
        s = sun(city.observer, date=dt_object.date(), tzinfo=dt_util.UTC)
        return s["sunrise"] <= dt_object <= s["sunset"]
    except Exception as e:
        _LOGGER.warning(f"Could not determine sun position for is_daytime: {e}")
        hour = dt_object.astimezone(dt_util.get_default_time_zone()).hour
        return 6 <= hour < 18

def condition_to_night_time(condition: Optional[str], dt: datetime.datetime) -> Optional[str]:
    if condition is None:
        return None
    latitude_fixed = 46.0569 
    longitude_fixed = 14.5058
    if condition == ATTR_CONDITION_SUNNY and not is_daytime(dt, latitude_fixed, longitude_fixed):
        return ATTR_CONDITION_CLEAR_NIGHT
    return condition
