"""Sensor platform for ARSO Weather integration."""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import homeassistant.util.dt as dt_util
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    CONF_LOCATION,
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CONF_ENABLE_MOUNTAIN,
    CONF_MOUNTAIN_REGION,
    DEFAULT_MOUNTAIN_REGION,
    DOMAIN,
    MOUNTAIN_COORDINATOR_KEY,
    MOUNTAIN_DEVICE_SUFFIX,
)
from .coordinator import ArsoDataUpdateCoordinator

# --- Določanje konstant glede na verzijo Home Assistant ---
try:
    # Za novejše verzije HA (2024.x+)
    from homeassistant.const import UnitOfVolumetricFlux as _UOVF

    UNIT_MM_PER_HOUR = _UOVF.MILLIMETERS_PER_HOUR
    PRECIP_INTENSITY_CLASS = SensorDeviceClass.PRECIPITATION_INTENSITY
except (ImportError, AttributeError):
    # Fallback za starejše verzije HA
    UNIT_MM_PER_HOUR = "mm/h"
    PRECIP_INTENSITY_CLASS = None  # Brez posebnega device_class

_LOGGER = logging.getLogger(__name__)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Varno vrne vrednost atributa ali ključa iz slovarja, sicer privzeto vrednost."""
    if obj is None:
        return default
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


# --- Opisi senzorjev za trenutno vreme ('current') ---
SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="relative_humidity_percent",
        name="Relative Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="mean_sea_level_pressure_hpa",
        name="Mean Sea Level Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="wind_speed_kmh",
        name="Wind Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key="wind_direction_text",
        name="Wind Direction",
        icon="mdi:compass-outline",
    ),
    SensorEntityDescription(
        key="max_wind_gust_kmh",
        name="Wind Gust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
    ),
    SensorEntityDescription(
        key="dew_point",
        name="Dew Point",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="wind_direction_degrees",
        name="Wind Direction Degrees",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass",
    ),
    SensorEntityDescription(
        key="station_pressure_hpa",
        name="Station Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_accumulated_mm",
        name="Precipitation (10 min)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_rate",
        name="Precipitation Rate",
        native_unit_of_measurement=UNIT_MM_PER_HOUR,
        device_class=PRECIP_INTENSITY_CLASS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="snow_depth_cm",
        name="Snow Depth",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-snowy",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="global_solar_radiation_wm2",
        name="Global Solar Radiation",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant-outline",
    ),
    SensorEntityDescription(
        key="visibility_km",
        name="Visibility",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:eye-outline",
    ),
    SensorEntityDescription(
        key="current_uv_index",
        name="Current UV Index",
        icon="mdi:sunglasses",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="uv_index_today",
        name="UV Index Today",
        icon="mdi:sun-wireless",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Nastavi senzorje ARSO na podlagi konfiguracijskega vnosa."""
    coordinator: ArsoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    location_name = entry.data[CONF_LOCATION]

    entities: list[SensorEntity] = []

    # Naprava za lokacijo
    device_info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"ARSO Weather – {location_name}",
        manufacturer="ARSO",
        model="Weather Sensors",
    )

    # Ustvari senzorje za trenutno stanje
    current_list = (coordinator.data or {}).get("current", [])
    current = current_list[0] if current_list else None
    if current:
        for desc in SENSOR_DESCRIPTIONS:
            if desc.key == "uv_index_today":
                continue  # Obdelamo posebej
            if _get(current, desc.key) is not None:
                entities.append(
                    ArsoWeatherSensor(coordinator, desc, device_info, entry.entry_id)
                )
            else:
                _LOGGER.debug(
                    "Skipping sensor %s for %s (no value)", desc.key, location_name
                )
    else:
        _LOGGER.info("No 'current' data available yet for %s", location_name)

    # Senzor za današnji UV indeks iz napovedi
    if (coordinator.data or {}).get("forecast24h"):
        uv_desc = next(
            (d for d in SENSOR_DESCRIPTIONS if d.key == "uv_index_today"), None
        )
        if uv_desc:
            entities.append(
                ArsoUVIndexTodaySensor(coordinator, uv_desc, device_info, entry.entry_id)
            )

    # Senzorji za gore (če so omogočeni)
    options = entry.options or {}
    if options.get(CONF_ENABLE_MOUNTAIN, False):
        mcoord_key = MOUNTAIN_COORDINATOR_KEY.format(entry.entry_id)
        if mcoord := hass.data[DOMAIN].get(mcoord_key):
            region = options.get(CONF_MOUNTAIN_REGION, DEFAULT_MOUNTAIN_REGION)
            entities.append(MountainForecastRawSensor(mcoord, entry, region))
        else:
            _LOGGER.debug(
                "Mountain coordinator not found for %s", entry.entry_id
            )

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d ARSO sensors for %s", len(entities), location_name)
    else:
        _LOGGER.warning("No sensors created for %s at setup time", location_name)


class ArsoWeatherSensor(CoordinatorEntity[ArsoDataUpdateCoordinator], SensorEntity):
    """Splošni senzor ARSO za trenutne vremenske podatke."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ArsoDataUpdateCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        config_entry_id: str,
    ) -> None:
        """Inicializacija senzorja."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{description.key}"
        self._attr_attribution = (
            "UV data: Temis.nl; other: ARSO"
            if description.key == "current_uv_index"
            else "Source: ARSO"
        )

    @property
    def native_value(self) -> Any:
        """Vrne vrednost senzorja."""
        current_list = (self.coordinator.data or {}).get("current", [])
        current = current_list[0] if current_list else None
        if not current:
            return None

        value = _get(current, self.entity_description.key)
        precision = self.entity_description.suggested_display_precision
        if precision is not None and isinstance(value, (int, float)):
            return round(value, precision)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Vrne dodatne atribute stanja."""
        current_list = (self.coordinator.data or {}).get("current", [])
        current = current_list[0] if current_list else None
        if not current:
            return None

        attrs: dict[str, Any] = {}
        if valid_time := _get(current, "valid_time"):
            try:
                attrs["last_updated_from_source"] = dt_util.as_local(
                    valid_time
                ).isoformat()
            except (TypeError, ValueError):
                attrs["last_updated_from_source"] = str(valid_time)
        return attrs or None

    @property
    def available(self) -> bool:
        """Vrne True, če je entiteta na voljo."""
        if not super().available:
            return False
        current_list = (self.coordinator.data or {}).get("current", [])
        current = current_list[0] if current_list else None
        if not current:
            return False
        return _get(current, self.entity_description.key) is not None


class ArsoUVIndexTodaySensor(CoordinatorEntity[ArsoDataUpdateCoordinator], SensorEntity):
    """Senzor za današnji UV indeks, pridobljen iz 24-urne napovedi."""

    _attr_has_entity_name = True
    _attr_attribution = "UV data: Temis.nl (if present); forecast framework: ARSO"

    def __init__(
        self,
        coordinator: ArsoDataUpdateCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        config_entry_id: str,
    ) -> None:
        """Inicializacija senzorja."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Vrne najvišji UV indeks za današnji dan."""
        forecast_data = (self.coordinator.data or {}).get("forecast24h", [])
        if not forecast_data:
            return None

        today = dt_util.now().date()
        max_uv: float | None = None

        for item in forecast_data:
            if not (valid_time := _get(item, "valid_time")):
                continue
            try:
                if dt_util.as_local(valid_time).date() != today:
                    continue
            except (TypeError, ValueError):
                continue

            if (uv_val := _get(item, "uv_index")) is not None and isinstance(
                uv_val, (int, float)
            ):
                max_uv = uv_val if max_uv is None else max(max_uv, float(uv_val))

        return max_uv

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Vrne dodatne atribute stanja."""
        forecast_data = (self.coordinator.data or {}).get("forecast24h", [])
        if not forecast_data:
            return None

        today = dt_util.now().date()
        for item in forecast_data:
            if valid_time := _get(item, "valid_time"):
                try:
                    if dt_util.as_local(valid_time).date() == today:
                        return {
                            "forecast_valid_time": dt_util.as_local(
                                valid_time
                            ).isoformat()
                        }
                except (TypeError, ValueError):
                    continue
        return None

    @property
    def available(self) -> bool:
        """Vrne True, če je entiteta na voljo."""
        return super().available and bool(
            (self.coordinator.data or {}).get("forecast24h")
        )


# --- Senzorji za gorsko napoved ---
ATTR_SOURCE_URL = "source_url"
ATTR_UPDATED_AT = "updated_at_utc"
ATTR_HTML_PREVIEW = "raw_html_preview"
ATTR_HTML_LEN = "raw_html_length"


class MountainBaseEntity(CoordinatorEntity[DataUpdateCoordinator], SensorEntity):
    """Osnovna entiteta za senzorje gorske napovedi."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, region: str
    ) -> None:
        """Inicializacija osnovne entitete."""
        super().__init__(coordinator)
        self._entry = entry
        self._region = region

    @property
    def device_info(self) -> DeviceInfo:
        """Vrne informacije o napravi."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}-{MOUNTAIN_DEVICE_SUFFIX}")},
            name=f"ARSO Mountain – {self._region}",
            manufacturer="ARSO",
            model="Mountain forecast",
        )


class MountainForecastRawSensor(MountainBaseEntity):
    """Senzor, ki prikaže surov predogled HTML vsebine gorske napovedi."""

    _attr_name = "Forecast (raw preview)"
    _attr_icon = "mdi:mountain"

    def __init__(
        self, coordinator: DataUpdateCoordinator, entry: ConfigEntry, region: str
    ) -> None:
        """Inicializacija senzorja."""
        super().__init__(coordinator, entry, region)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{MOUNTAIN_DEVICE_SUFFIX}_raw"

    @property
    def native_value(self) -> str | None:
        """Vrne stanje senzorja."""
        return "available" if self.coordinator.data else "unavailable"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Vrne dodatne atribute stanja."""
        data = self.coordinator.data or {}
        attrs: dict[str, Any] = {
            ATTR_ATTRIBUTION: "Source: ARSO",
            ATTR_SOURCE_URL: data.get("source_url"),
            ATTR_UPDATED_AT: data.get("updated_at_utc"),
            ATTR_HTML_LEN: data.get("raw_html_length"),
        }
        if preview := data.get("raw_html_preview"):
            attrs[ATTR_HTML_PREVIEW] = preview
        return attrs
