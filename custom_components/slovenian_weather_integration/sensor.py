import logging
from datetime import datetime
from typing import Optional, Dict, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    CONF_LOCATION,
    UnitOfTemperature,
    UnitOfSpeed,
    UnitOfPressure,
    UnitOfLength,
    PERCENTAGE,
    DEGREE,
    UnitOfIrradiance,
    UnitOfPrecipitationDepth,
    UnitOfVolumetricFlux,
)
from homeassistant.helpers.device_registry import DeviceInfo
import homeassistant.util.dt as dt_util  # For timezone conversion

# Assuming your coordinator and constants are defined here
from .coordinator import ArsoDataUpdateCoordinator  # Adjust import if structure differs
from .const import DOMAIN

# Import your library's model
from .arso_weather.models import ObservationDetails

_LOGGER = logging.getLogger(__name__)

# Define Sensor Descriptions using the Pydantic field names as keys
# We will filter this list based on available data later
SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    # --- Fields from BaseTimelineEntry ---
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
        suggested_display_precision=1,  # Often has decimals, e.g. 1022.6
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
        # No unit, device_class, or state_class for textual direction
    ),
    SensorEntityDescription(
        key="max_wind_gust_kmh",
        name="Wind Gust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
    ),
    # --- Fields specific to ObservationDetails ---
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
        key="wind_direction_max_gust_degrees",
        name="Wind Gust Direction Degrees",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-rose",
        entity_registry_enabled_default=False,
    ),
    # wind_direction_max_gust_text covered by wind_direction_text generally
    SensorEntityDescription(
        key="wind_speed_average_kmh",
        name="Wind Speed Average",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        entity_registry_enabled_default=False,  # Often less critical than current speed/gust
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
        key="precipitation_accumulated_mm",  # 10 minute accumulated rainfall
        name="Precipitation 10 minutes",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,  # represents a total over a period that might reset (e.g., daily)
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_rate",
        name="Precipitation Rate",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
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
        key="precipitation_1h_accumulated_mm",
        name="Precipitation 1h",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,  # Total over the last hour
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_12h_accumulated_mm",
        name="Precipitation 12h",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,  # Total over the last 12 hours (since 6/18 UTC)
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_24h_accumulated_mm",
        name="Precipitation 24h",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,  # Total over the last 24 hours
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="water_temperature",
        name="Water Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-water",
        suggested_display_precision=1,
        entity_registry_enabled_default=False,  # Often specific to certain locations
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
        key="global_solar_radiation_average_wm2",
        name="Global Solar Radiation Average",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="diffuse_solar_radiation_wm2",
        name="Diffuse Solar Radiation",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-partly-cloudy",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="diffuse_solar_radiation_average_wm2",
        name="Diffuse Solar Radiation Average",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-partly-cloudy",
        entity_registry_enabled_default=False,
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
        key="temperature_at_5cm",
        name="Temperature at 5cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-low",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="temperature_average_at_5cm",
        name="Temperature Average at 5cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-low",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_at_5cm",
        name="Ground Temperature at 5cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_5cm",
        name="Ground Temperature Average at 5cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_at_10cm",
        name="Ground Temperature at 10cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_10cm",
        name="Ground Temperature Average at 10cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_at_20cm",
        name="Ground Temperature at 20cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_20cm",
        name="Ground Temperature Average at 20cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_at_30cm",
        name="Ground Temperature at 30cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_30cm",
        name="Ground Temperature Average at 30cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_at_50cm",
        name="Ground Temperature at 50cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_50cm",
        name="Ground Temperature Average at 50cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO weather sensor entities based on a config entry."""
    coordinator: ArsoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    location_name = entry.data[CONF_LOCATION]  # Get location name from config entry

    if not coordinator.last_update_success or not coordinator.data:
        _LOGGER.warning(
            "Initial ARSO data fetch failed or missing, cannot set up sensors yet."
        )
        if not coordinator.data:  # Strict check if no data object exists
            _LOGGER.error(
                "No initial data object from coordinator. Cannot create sensors."
            )
            return  # Cannot proceed without initial data structure

    current_data: ObservationDetails = coordinator.data.get("current")[0]
    _LOGGER.debug(f"DATA IS {current_data}")
    entities_to_add = []

    # Standard device info for all sensors related to this location
    device_info = DeviceInfo(
        identifiers={(DOMAIN, location_name)},
        name=location_name,
        manufacturer="ARSO",
        model="Weather Station",
        entry_type="service",
    )

    # Create entities for standard descriptions if data is available
    for description in SENSOR_DESCRIPTIONS:
        # Check if the key exists in the Pydantic model and its value is not None
        value = getattr(current_data, description.key, None)
        if value is not None:
            _LOGGER.debug(f"Creating entity for {description.key} (value: {value})")
            entities_to_add.append(
                ArsoWeatherSensor(coordinator, description, device_info, entry.entry_id)
            )
        else:
            _LOGGER.debug(
                f"Skipping entity creation for {description.key} (value is None)"
            )

    if entities_to_add:
        _LOGGER.info(
            f"Adding {len(entities_to_add)} ARSO weather sensors for {location_name}"
        )
        async_add_entities(entities_to_add)
    else:
        _LOGGER.warning(
            f"No valid sensors found to add for {location_name} based on initial data."
        )


class ArsoWeatherSensor(CoordinatorEntity[ArsoDataUpdateCoordinator], SensorEntity):
    """Implementation of an ARSO weather sensor."""

    _attr_has_entity_name = True  # Use entity description name as the base
    # _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: ArsoDataUpdateCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        config_entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        # Construct unique ID: domain_configentryid_sensorkey
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{description.key}"

    @property
    def native_value(self) -> Optional[Any]:
        """Return the state of the sensor."""
        if not self.coordinator.last_update_success or not self.coordinator.data.get(
            "current"
        ):
            return None  # Let HA handle unavailability

        current_data: ObservationDetails = self.coordinator.data.get("current")[0]

        # Default handling: get value directly using the key
        value = getattr(current_data, self.entity_description.key, None)

        # Apply suggested precision if available and value is numeric
        precision = self.entity_description.suggested_display_precision
        if precision is not None and isinstance(value, (int, float)):
            return round(value, precision)

        return (
            value  # Return string as is (e.g., cardinal direction) or None if missing
        )

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return entity specific state attributes."""
        if not self.coordinator.last_update_success or not self.coordinator.data.get(
            "current"
        ):
            return None  # Let HA handle unavailability

        current_data: ObservationDetails = self.coordinator.data.get("current")[0]
        valid_utc: Optional[datetime] = getattr(current_data, "valid", None)

        if valid_utc:
            # Convert the UTC datetime object from the API to local time
            local_valid_time = dt_util.as_local(valid_utc)
            return {"last_updated": local_valid_time.isoformat()}
        else:
            return None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Available if the coordinator is successful and the specific value is not None
        # (or if it's the special rate sensor and its ingredients are available)
        base_available = super().available and self.coordinator.data is not None

        if not base_available:
            return False

        return (
            getattr(
                self.coordinator.data.get("current")[0],
                self.entity_description.key,
                None,
            )
            is not None
        )
