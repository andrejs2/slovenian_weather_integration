import logging
from datetime import datetime, date # Added date
from typing import Optional, Dict, Any, cast

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
    # Consider EntityCategory if some sensors are for diagnostics/config
    # from homeassistant.helpers.entity import EntityCategory
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
import homeassistant.util.dt as dt_util # Already imported

from .coordinator import ArsoDataUpdateCoordinator
from .const import DOMAIN

# Import your library's models
from .arso_weather.models import ObservationDetails, Forecast24hTimelineEntry # Added Forecast24hTimelineEntry

_LOGGER = logging.getLogger(__name__)

# Define Sensor Descriptions using the Pydantic field names as keys
SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    # --- Fields from BaseTimelineEntry / ObservationDetails ---
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
        key="wind_direction_text", # From BaseTimelineEntry
        name="Wind Direction",
        icon="mdi:compass-outline",
    ),
    SensorEntityDescription(
        key="max_wind_gust_kmh", # From BaseTimelineEntry
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
        key="station_pressure_hpa",
        name="Station Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_accumulated_mm", # 10 minute accumulated rainfall from ObservationDetails
        name="Precipitation (10 min)", # Clarified name
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING, # More appropriate for accumulating sensor
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_rate", # Computed field in ObservationDetails
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
        device_class=SensorDeviceClass.DISTANCE, # DISTANCE is more generic than VISIBILITY for device class
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:eye-outline",
    ),
    # --- NEW SENSOR: Current UV Index (from ObservationDetails) ---
    SensorEntityDescription(
        key="current_uv_index", # This key must match the field name in ObservationDetails model
        name="Current UV Index",
        icon="mdi:sun-alert-outline", # Using a more specific icon for UV alert
        state_class=SensorStateClass.MEASUREMENT,
        # No native_unit_of_measurement for UV index, it's a dimensionless number
        # entity_category=EntityCategory.MEASUREMENT, # Default category
    ),
    # --- Other existing sensors from your original list can be added here if data is available ---
    # Example:
    # SensorEntityDescription(
    #     key="precipitation_1h_accumulated_mm",
    #     name="Precipitation 1h",
    #     # ... other properties
    # ),

    # --- NEW SENSOR DESCRIPTION for UV Index Today (will use a dedicated class) ---
    SensorEntityDescription(
        key="uv_index_today", # Unique key for this specific sensor logic
        name="UV Index Today",
        icon="mdi:sun-calendar", # Icon indicating daily UV
        state_class=SensorStateClass.MEASUREMENT,
        # No native_unit_of_measurement for UV index
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO weather sensor entities based on a config entry."""
    coordinator: ArsoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    location_name = entry.data[CONF_LOCATION]

    entities_to_add: list[SensorEntity] = [] # Explicitly list[SensorEntity]

    # Standard device info for all sensors related to this location
    device_info = DeviceInfo(
        identifiers={(DOMAIN, location_name)}, # Use location_name for consistency
        name=f"ARSO Weather {location_name}", # Device name includes location
        manufacturer="ARSO & Temis.nl", # Added Temis.nl as a source
        model="Weather Sensors",
        entry_type="service", # Default entry type
        # configuration_url="YOUR_INTEGRATION_DOC_URL", # Optional: Link to docs
    )

    # --- Create standard sensors from ObservationDetails ---
    if coordinator.data and coordinator.data.get("current"):
        current_data_list = coordinator.data.get("current", [])
        if current_data_list and isinstance(current_data_list[0], ObservationDetails):
            current_obs_data: ObservationDetails = current_data_list[0]
            
            for description in SENSOR_DESCRIPTIONS:
                # Skip the "uv_index_today" description here, it's handled separately
                if description.key == "uv_index_today":
                    continue

                # Check if the key exists in the ObservationDetails model and its value is not None
                # This will now also pick up "current_uv_index" if that field exists in current_obs_data
                if hasattr(current_obs_data, description.key):
                    value = getattr(current_obs_data, description.key, None)
                    if value is not None:
                        _LOGGER.debug(f"Creating ArsoWeatherSensor for '{description.key}' (value: {value}) for {location_name}")
                        entities_to_add.append(
                            ArsoWeatherSensor(coordinator, description, device_info, entry.entry_id)
                        )
                    else:
                        _LOGGER.debug(f"Skipping ArsoWeatherSensor for '{description.key}' (value is None) for {location_name}")
                else:
                    _LOGGER.debug(f"Attribute '{description.key}' not found in ObservationDetails for {location_name}")
        else:
            _LOGGER.warning(f"No 'current' ObservationDetails data available to set up standard sensors for {location_name}.")

    # --- Create UV Index Today sensor ---
    # This sensor reads from the 'forecast24h' data provided by the coordinator
    uv_today_description = next((desc for desc in SENSOR_DESCRIPTIONS if desc.key == "uv_index_today"), None)
    if uv_today_description:
        # Check if forecast24h data is available and contains the necessary info
        if coordinator.data and coordinator.data.get("forecast24h"):
            forecast_data_list = coordinator.data.get("forecast24h", [])
            # We don't need to check the content here, the sensor itself will determine availability
            _LOGGER.debug(f"Creating ArsoUVIndexTodaySensor for {location_name}")
            entities_to_add.append(
                ArsoUVIndexTodaySensor(coordinator, uv_today_description, device_info, entry.entry_id)
            )
        else:
            _LOGGER.info(f"No 'forecast24h' data available to set up UV Index Today sensor for {location_name}.")


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
    """Implementation of a generic ARSO weather sensor based on ObservationDetails."""

    _attr_has_entity_name = True
    # _attr_attribution = "Data provided by ARSO" # General attribution

    def __init__(
        self,
        coordinator: ArsoDataUpdateCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        config_entry_id: str, # Changed from entry.entry_id to config_entry_id for clarity
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        # Construct unique ID: domain_configentryid_sensorkey
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{description.key}"
        self._config_entry_id = config_entry_id # Store for potential use

        # Set attribution based on sensor key
        if description.key == "current_uv_index":
            self._attr_attribution = "UV Index data from Temis.nl, other data from ARSO"
        else:
            self._attr_attribution = "Data provided by ARSO"


    @property
    def native_value(self) -> Optional[Any]:
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.get("current"):
            return None

        current_data_list = self.coordinator.data.get("current", [])
        if not current_data_list or not isinstance(current_data_list[0], ObservationDetails):
            return None
        
        current_obs_data: ObservationDetails = current_data_list[0]
        
        value = getattr(current_obs_data, self.entity_description.key, None)

        precision = self.entity_description.suggested_display_precision
        if precision is not None and isinstance(value, (int, float)):
            return round(value, precision)
        return value

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return entity specific state attributes."""
        # Only add last_updated if it's relevant for this specific sensor's source data
        # For most sensors based on ObservationDetails, 'valid_time' is the relevant timestamp.
        if not self.coordinator.data or not self.coordinator.data.get("current"):
            return None
        
        current_data_list = self.coordinator.data.get("current", [])
        if not current_data_list or not isinstance(current_data_list[0], ObservationDetails):
            return None
            
        current_obs_data: ObservationDetails = current_data_list[0]
        
        attrs: dict[str, Any] = {}
        # Add 'last_updated_from_source' based on the 'valid_time' of the ObservationDetails
        if current_obs_data.valid_time:
            attrs["last_updated_from_source"] = dt_util.as_local(current_obs_data.valid_time).isoformat()
        
        return attrs if attrs else None


    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available or not self.coordinator.data or not self.coordinator.data.get("current"):
            return False
        
        current_data_list = self.coordinator.data.get("current", [])
        if not current_data_list or not isinstance(current_data_list[0], ObservationDetails):
            return False
        
        current_obs_data: ObservationDetails = current_data_list[0]
        
        # Check if the specific key for this sensor exists and has a non-None value
        return hasattr(current_obs_data, self.entity_description.key) and \
               getattr(current_obs_data, self.entity_description.key, None) is not None


class ArsoUVIndexTodaySensor(CoordinatorEntity[ArsoDataUpdateCoordinator], SensorEntity):
    """Sensor for today's UV Index, derived from the 24h forecast data."""

    _attr_has_entity_name = True
    _attr_attribution = "UV Index data from Temis.nl, forecast framework by ARSO"

    def __init__(
        self,
        coordinator: ArsoDataUpdateCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        config_entry_id: str,
    ) -> None:
        """Initialize the UV Index Today sensor."""
        super().__init__(coordinator)
        self.entity_description = description # Should be the "uv_index_today" SENSOR_DESCRIPTION
        self._attr_device_info = device_info
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{description.key}"
        self._config_entry_id = config_entry_id

    @property
    def native_value(self) -> Optional[float]:
        """Return today's UV index from the forecast24h data."""
        if not self.coordinator.data or not self.coordinator.data.get("forecast24h"):
            _LOGGER.debug(f"UV Today Sensor: No 'forecast24h' data available for {self._attr_unique_id}")
            return None

        forecast_list: list[Any] = self.coordinator.data.get("forecast24h", [])
        today_local_date: date = dt_util.now().date() # Get current local date

        for forecast_entry_model in forecast_list:
            if isinstance(forecast_entry_model, Forecast24hTimelineEntry):
                # valid_time in Forecast24hTimelineEntry should be a datetime object (UTC)
                if forecast_entry_model.valid_time:
                    forecast_date_local = dt_util.as_local(forecast_entry_model.valid_time).date()
                    if forecast_date_local == today_local_date:
                        # The 'uv_index' attribute should exist on Forecast24hTimelineEntry
                        # as per changes in models.py and client.py
                        if hasattr(forecast_entry_model, 'uv_index') and forecast_entry_model.uv_index is not None:
                            _LOGGER.debug(f"UV Today Sensor ({self._attr_unique_id}): Found UV index {forecast_entry_model.uv_index} for {today_local_date}")
                            return cast(float, forecast_entry_model.uv_index)
                        else:
                            _LOGGER.debug(f"UV Today Sensor ({self._attr_unique_id}): 'uv_index' attribute missing or None for today's forecast ({today_local_date}).")
                            return None # Explicitly no UV index for today
        
        _LOGGER.debug(f"UV Today Sensor ({self._attr_unique_id}): No forecast entry found for today ({today_local_date}).")
        return None # No forecast found for today

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return entity specific state attributes."""
        # Could add the source valid_time of the forecast entry used, if desired.
        if self.native_value is not None and self.coordinator.data and self.coordinator.data.get("forecast24h"):
            forecast_list: list[Any] = self.coordinator.data.get("forecast24h", [])
            today_local_date: date = dt_util.now().date()
            for forecast_entry_model in forecast_list:
                if isinstance(forecast_entry_model, Forecast24hTimelineEntry) and forecast_entry_model.valid_time:
                    if dt_util.as_local(forecast_entry_model.valid_time).date() == today_local_date:
                        return {"forecast_valid_time": dt_util.as_local(forecast_entry_model.valid_time).isoformat()}
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available (i.e., data for today can be determined)."""
        if not super().available or not self.coordinator.data or not self.coordinator.data.get("forecast24h"):
            return False
        
        # Sensor is available if there's forecast data; native_value will be None if today's UV isn't found.
        # A more precise availability would be if native_value is not None, but HA handles that.
        # For now, if forecast24h exists, we consider the sensor potentially able to find data.
        return bool(self.coordinator.data.get("forecast24h"))
