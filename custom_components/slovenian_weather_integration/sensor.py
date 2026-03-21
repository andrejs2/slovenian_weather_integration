"""Sensor platform for the Slovenian Weather Integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
    CONF_LOCATION,
    DEGREE,
    PERCENTAGE,
    UnitOfIrradiance,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolumetricFlux,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
import homeassistant.util.dt as dt_util

from .arso_weather.agrometeo_client import AGRO_STATIONS
from .arso_weather.air_quality_client import AQ_STATIONS, EAQI_LABELS, compute_eaqi
from .arso_weather.utci_client import UTCI_STATIONS
from .arso_weather.mountain_client import MOUNTAIN_REGIONS
from .arso_weather.ski_client import SKI_RESORTS
from .arso_weather.avalanche_client import AVALANCHE_REGIONS
from .arso_weather.warnings_client import WARNING_REGIONS, WARNING_TYPES
from .const import (
    DOMAIN,
    MODULE_AGROMETEO,
    MODULE_AIR_QUALITY,
    MODULE_AVALANCHE,
    MODULE_BIO_WEATHER,
    MODULE_MOUNTAIN,
    MODULE_SKI,
    MODULE_TEXT_FORECAST,
    MODULE_UTCI,
    MODULE_WARNINGS,
    ArsoConfigEntry,
    get_enabled_modules,
)
from .coordinator import (
    ArsoDataUpdateCoordinator,
    CONF_AGRO_STATIONS,
    CONF_AQ_STATIONS,
    CONF_AVALANCHE_REGIONS,
    CONF_MOUNTAIN_REGIONS,
    CONF_UTCI_STATIONS,
)
from .arso_weather.models import ObservationDetails

_LOGGER = logging.getLogger(__name__)

# All 35 sensor description keys are FROZEN for backwards compatibility.
# See docs/backwards_compatibility.md — never change existing key values.
SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    # --- Fields from BaseTimelineEntry ---
    SensorEntityDescription(
        key="temperature",
        name="Temperatura",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="relative_humidity_percent",
        name="Relativna vlažnost",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="mean_sea_level_pressure_hpa",
        name="Zračni tlak",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="wind_speed_kmh",
        name="Hitrost vetra",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key="wind_direction_text",
        name="Smer vetra",
        icon="mdi:compass-outline",
    ),
    SensorEntityDescription(
        key="max_wind_gust_kmh",
        name="Sunki vetra",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
    ),
    SensorEntityDescription(
        key="pressure_tendency",
        name="Tendenca tlaka",
        icon="mdi:trending-up",
    ),
    SensorEntityDescription(
        key="weather_phenomenon",
        name="Vremenski pojav",
        icon="mdi:weather-partly-rainy",
    ),
    # --- Fields specific to ObservationDetails ---
    SensorEntityDescription(
        key="dew_point",
        name="Rosišče",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="wind_direction_degrees",
        name="Smer vetra (stopinje)",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass",
    ),
    SensorEntityDescription(
        key="wind_direction_max_gust_degrees",
        name="Smer sunkov (stopinje)",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass-rose",
    ),
    SensorEntityDescription(
        key="wind_speed_average_kmh",
        name="Povprečna hitrost vetra",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key="station_pressure_hpa",
        name="Tlak na postaji",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_accumulated_mm",
        name="Padavine 10 min",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_rate",
        name="Intenzivnost padavin",
        native_unit_of_measurement=UnitOfVolumetricFlux.MILLIMETERS_PER_HOUR,
        device_class=SensorDeviceClass.PRECIPITATION_INTENSITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="snow_depth_cm",
        name="Višina snega",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-snowy",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_1h_accumulated_mm",
        name="Padavine 1h",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_12h_accumulated_mm",
        name="Padavine 12h",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="precipitation_24h_accumulated_mm",
        name="Padavine 24h",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="water_temperature",
        name="Temperatura vode",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-water",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="global_solar_radiation_wm2",
        name="Globalno sončno sevanje",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant-outline",
    ),
    SensorEntityDescription(
        key="global_solar_radiation_average_wm2",
        name="Povpr. globalno sončno sevanje",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:solar-power-variant",
    ),
    SensorEntityDescription(
        key="diffuse_solar_radiation_wm2",
        name="Difuzno sončno sevanje",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-partly-cloudy",
    ),
    SensorEntityDescription(
        key="diffuse_solar_radiation_average_wm2",
        name="Povpr. difuzno sončno sevanje",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-partly-cloudy",
    ),
    SensorEntityDescription(
        key="visibility_km",
        name="Vidljivost",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:eye-outline",
    ),
    SensorEntityDescription(
        key="temperature_at_5cm",
        name="Temperatura na 5 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-low",
    ),
    SensorEntityDescription(
        key="temperature_average_at_5cm",
        name="Povpr. temperatura na 5 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-low",
    ),
    SensorEntityDescription(
        key="ground_temperature_at_5cm",
        name="Temperatura tal 5 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_5cm",
        name="Povpr. temperatura tal 5 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_at_10cm",
        name="Temperatura tal 10 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_10cm",
        name="Povpr. temperatura tal 10 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_at_20cm",
        name="Temperatura tal 20 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_20cm",
        name="Povpr. temperatura tal 20 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_at_30cm",
        name="Temperatura tal 30 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_30cm",
        name="Povpr. temperatura tal 30 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_at_50cm",
        name="Temperatura tal 50 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="ground_temperature_average_at_50cm",
        name="Povpr. temperatura tal 50 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:thermometer-lines",
    ),
)

# --- Text forecast sensors (use TextForecastCoordinator) ---
TEXT_FORECAST_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="forecast",
        name="Besedilna napoved",
        icon="mdi:text-long",
    ),
    SensorEntityDescription(
        key="summary",
        name="Povzetek",
        icon="mdi:text-short",
    ),
    SensorEntityDescription(
        key="outlook",
        name="Obeti",
        icon="mdi:crystal-ball",
    ),
    SensorEntityDescription(
        key="weather_image",
        name="Vremenska slika",
        icon="mdi:weather-partly-cloudy",
    ),
)

# --- Bio-weather sensors (use BioWeatherCoordinator) ---
BIO_WEATHER_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="bio_weather",
        name="Biovreme",
        icon="mdi:heart-pulse",
    ),
    SensorEntityDescription(
        key="uv_index",
        name="UV indeks",
        icon="mdi:sun-wireless",
    ),
    SensorEntityDescription(
        key="pollen",
        name="Cvetni prah",
        icon="mdi:flower-pollen",
    ),
)

# --- Mountain forecast sensors (use MountainForecastCoordinator) ---
MOUNTAIN_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="today",
        name="Gorska napoved danes",
        icon="mdi:image-filter-hdr",
    ),
    SensorEntityDescription(
        key="tomorrow",
        name="Gorska napoved jutri",
        icon="mdi:image-filter-hdr-outline",
    ),
    SensorEntityDescription(
        key="uvod",
        name="Gorska napoved pregled",
        icon="mdi:text-box-outline",
    ),
    SensorEntityDescription(
        key="zakljucek",
        name="Gorska napoved priporočila",
        icon="mdi:hiking",
    ),
)

# Config option key for selected ski resorts (must match config_flow)
CONF_SKI_RESORTS = "ski_resorts"

# --- Agrometeo sensor descriptions (per-station, disabled by default) ---
AGRO_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="tg_5_cm",
        name="Temperatura tal 5 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="tg_10_cm",
        name="Temperatura tal 10 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="tg_30_cm",
        name="Temperatura tal 30 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-lines",
    ),
    SensorEntityDescription(
        key="tn_5_cm",
        name="Min temperatura 5 cm",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-alert",
    ),
    SensorEntityDescription(
        key="etp",
        name="Evapotranspiracija",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-thermometer",
    ),
    SensorEntityDescription(
        key="wBal",
        name="Vodna bilanca",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
    ),
)


# --- Air quality sensor descriptions (per-station, disabled by default) ---
AQ_SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="pm10",
        name="PM10",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="pm2.5",
        name="PM2.5",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="o3",
        name="Ozon (O3)",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="no2",
        name="Dušikov dioksid (NO2)",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="so2",
        name="Žveplov dioksid (SO2)",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        suggested_display_precision=1,
    ),
    SensorEntityDescription(
        key="co",
        name="Ogljikov monoksid (CO)",
        native_unit_of_measurement=CONCENTRATION_MILLIGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule-co",
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ArsoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ARSO weather sensor entities based on a config entry."""
    coordinator = entry.runtime_data.coordinator
    location_name = entry.data[CONF_LOCATION]
    modules = get_enabled_modules(entry)

    device_info = DeviceInfo(
        identifiers={(DOMAIN, location_name)},
        name="ARSO Weather " + location_name,
        manufacturer="ARSO",
        model="Vremenska postaja",
        entry_type="service",
    )

    entities: list[SensorEntity] = []

    # --- Weather sensors (always enabled) ---
    # Only create sensors for which the station has data in the initial fetch.
    current_data = None
    if coordinator.data and (current_list := coordinator.data.get("current")):
        if current_list:
            current_data = current_list[0]

    for description in SENSOR_DESCRIPTIONS:
        if current_data is not None:
            value = getattr(current_data, description.key, None)
            if value is None:
                _LOGGER.debug("Skipping sensor %s (no initial data)", description.key)
                continue
        entities.append(
            ArsoWeatherSensor(coordinator, description, device_info, entry.entry_id)
        )

    # --- Text forecast sensors ---
    if modules.get(MODULE_TEXT_FORECAST):
        tf_coord = entry.runtime_data.text_forecast_coordinator
        if tf_coord and tf_coord.data:
            tf_device_info = DeviceInfo(
                identifiers={(DOMAIN, "text_forecast")},
                name="ARSO Besedilna napoved",
                manufacturer="ARSO",
                model="Besedilna napoved",
                entry_type="service",
            )
            for description in TEXT_FORECAST_SENSOR_DESCRIPTIONS:
                if tf_coord.data.get(description.key) is not None:
                    entities.append(
                        ArsoTextSensor(
                            tf_coord, description, tf_device_info,
                            entry.entry_id, "tf",
                        )
                    )

    # --- Bio-weather sensors ---
    if modules.get(MODULE_BIO_WEATHER):
        bio_coord = entry.runtime_data.bio_weather_coordinator
        if bio_coord and bio_coord.data:
            bio_device_info = DeviceInfo(
                identifiers={(DOMAIN, "bio_weather")},
                name="ARSO Biovreme",
                manufacturer="ARSO",
                model="Biovreme",
                entry_type="service",
            )
            for description in BIO_WEATHER_SENSOR_DESCRIPTIONS:
                if bio_coord.data.get(description.key) is not None:
                    entities.append(
                        ArsoTextSensor(
                            bio_coord, description, bio_device_info,
                            entry.entry_id, "bio",
                        )
                    )

    # --- Mountain forecast sensors ---
    if modules.get(MODULE_MOUNTAIN):
        mtn_coord = entry.runtime_data.mountain_coordinator
        if mtn_coord and mtn_coord.data:
            mtn_device_info = DeviceInfo(
                identifiers={(DOMAIN, "mountain")},
                name="ARSO Gorski svet",
                manufacturer="ARSO",
                model="Gorska napoved",
                entry_type="service",
            )
            # Text forecast sensors (today/tomorrow)
            for description in MOUNTAIN_SENSOR_DESCRIPTIONS:
                if mtn_coord.data.get(description.key) is not None:
                    entities.append(
                        ArsoTextSensor(
                            mtn_coord, description, mtn_device_info,
                            entry.entry_id, "mtn",
                        )
                    )
            # Elevation sensors per selected region
            selected_regions = entry.options.get(CONF_MOUNTAIN_REGIONS, [])
            elevation_data = mtn_coord.data.get("elevation", {})
            for region_id in selected_regions:
                region_data = elevation_data.get(region_id, {})
                if region_data and region_data.get("current"):
                    display_name = region_data.get("region", region_id)
                    current = region_data.get("current", {})
                    # Overview sensor (enabled by default)
                    entities.append(
                        ArsoMountainOverviewSensor(
                            mtn_coord, mtn_device_info, entry.entry_id,
                            region_id, display_name,
                        )
                    )
                    # Individual temperature sensors (disabled by default)
                    for elev in _MTN_TEMP_ELEVATIONS:
                        if current.get(f"temp_{elev}m") is not None:
                            entities.append(
                                ArsoMountainTempSensor(
                                    mtn_coord, mtn_device_info,
                                    entry.entry_id, region_id,
                                    display_name, elev,
                                )
                            )
                    # Individual wind sensors (disabled by default)
                    for elev in _MTN_WIND_ELEVATIONS:
                        if current.get(f"wind_{elev}m_kmh") is not None:
                            entities.append(
                                ArsoMountainWindSensor(
                                    mtn_coord, mtn_device_info,
                                    entry.entry_id, region_id,
                                    display_name, elev,
                                )
                            )

    # --- Ski resort sensors ---
    if modules.get(MODULE_SKI):
        ski_coord = entry.runtime_data.ski_coordinator
        selected_resorts = entry.options.get(CONF_SKI_RESORTS, [])
        if ski_coord and ski_coord.data and selected_resorts:
            ski_device_info = DeviceInfo(
                identifiers={(DOMAIN, "ski_resorts")},
                name="ARSO Smučišča",
                manufacturer="ARSO",
                model="Smučišča",
                entry_type="service",
            )
            for display_name in selected_resorts:
                xml_key = SKI_RESORTS.get(display_name)
                if xml_key and xml_key.strip() in ski_coord.data:
                    entities.append(
                        ArsoSkiResortSensor(
                            ski_coord, ski_device_info, entry.entry_id,
                            display_name, xml_key.strip(),
                        )
                    )

    # --- Agrometeo sensors ---
    if modules.get(MODULE_AGROMETEO):
        agro_coord = entry.runtime_data.agrometeo_coordinator
        selected_agro = entry.options.get(CONF_AGRO_STATIONS, [])
        if agro_coord and agro_coord.data and selected_agro:
            agro_device_info = DeviceInfo(
                identifiers={(DOMAIN, "agrometeo")},
                name="ARSO Agrometeo",
                manufacturer="ARSO",
                model="Agrometeo",
                entry_type="service",
            )
            for station_name in selected_agro:
                if station_name not in agro_coord.data:
                    continue
                # Overview sensor (always enabled)
                entities.append(
                    ArsoAgrometeoOverviewSensor(
                        agro_coord, agro_device_info,
                        entry.entry_id, station_name,
                    )
                )
                # Individual value sensors (disabled by default)
                current = agro_coord.data[station_name].get("current", {})
                forecast = agro_coord.data[station_name].get("forecast", [])
                first_fc = forecast[0] if forecast else {}
                for desc in AGRO_SENSOR_DESCRIPTIONS:
                    if current.get(desc.key) is not None or first_fc.get(desc.key) is not None:
                        entities.append(
                            ArsoAgrometeoValueSensor(
                                agro_coord, agro_device_info,
                                entry.entry_id, station_name, desc,
                            )
                        )

    # --- UTCI sensors ---
    if modules.get(MODULE_UTCI):
        utci_coord = entry.runtime_data.utci_coordinator
        selected_utci = entry.options.get(CONF_UTCI_STATIONS, [])
        if utci_coord and utci_coord.data and selected_utci:
            utci_device_info = DeviceInfo(
                identifiers={(DOMAIN, "utci")},
                name="ARSO Toplotni občutek (UTCI)",
                manufacturer="ARSO",
                model="Toplotni občutek (UTCI)",
                entry_type="service",
            )
            for station_name in selected_utci:
                if station_name not in utci_coord.data:
                    continue
                entities.append(
                    ArsoUtciSensor(
                        utci_coord, utci_device_info,
                        entry.entry_id, station_name,
                    )
                )

    # --- Air quality sensors ---
    if modules.get(MODULE_AIR_QUALITY):
        aq_coord = entry.runtime_data.air_quality_coordinator
        selected_aq = entry.options.get(CONF_AQ_STATIONS, [])
        if aq_coord and aq_coord.data and selected_aq:
            aq_device_info = DeviceInfo(
                identifiers={(DOMAIN, "air_quality")},
                name="ARSO Kakovost zraka",
                manufacturer="ARSO",
                model="Kakovost zraka",
                entry_type="service",
            )
            for station_name in selected_aq:
                if station_name not in aq_coord.data:
                    continue
                # Overview sensor (always enabled)
                entities.append(
                    ArsoAirQualityOverviewSensor(
                        aq_coord, aq_device_info,
                        entry.entry_id, station_name,
                    )
                )
                # Individual pollutant sensors (disabled by default)
                hourly = aq_coord.data[station_name].get("hourly", {})
                for desc in AQ_SENSOR_DESCRIPTIONS:
                    if hourly.get(desc.key) is not None:
                        entities.append(
                            ArsoAirQualityValueSensor(
                                aq_coord, aq_device_info,
                                entry.entry_id, station_name, desc,
                            )
                        )

    # --- Avalanche sensors ---
    if modules.get(MODULE_AVALANCHE):
        aval_coord = entry.runtime_data.avalanche_coordinator
        selected_aval = entry.options.get(CONF_AVALANCHE_REGIONS, [])
        if aval_coord and aval_coord.data and selected_aval:
            aval_device_info = DeviceInfo(
                identifiers={(DOMAIN, "avalanche")},
                name="ARSO Snežni plazovi",
                manufacturer="ARSO",
                model="Snežni plazovi (EAWS)",
                entry_type="service",
            )
            for region_name in selected_aval:
                if region_name not in aval_coord.data:
                    continue
                entities.append(
                    ArsoAvalancheSensor(
                        aval_coord, aval_device_info,
                        entry.entry_id, region_name,
                    )
                )

    # --- Warnings sensor ---
    if modules.get(MODULE_WARNINGS):
        warn_coord = entry.runtime_data.warnings_coordinator
        if warn_coord:
            warn_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{location_name}_warnings")},
                name=f"ARSO Opozorila ({location_name})",
                manufacturer="ARSO",
                model="Vremenska opozorila",
                entry_type="service",
            )
            entities.append(
                ArsoWarningsOverviewSensor(
                    warn_coord, warn_device_info, entry.entry_id,
                    location_name,
                )
            )

    if entities:
        _LOGGER.info(
            "Adding %d ARSO sensors for %s", len(entities), location_name
        )
        async_add_entities(entities)
    else:
        _LOGGER.warning("No sensors with data for %s", location_name)


class ArsoWeatherSensor(
    CoordinatorEntity[ArsoDataUpdateCoordinator], SensorEntity
):
    """Implementation of an ARSO weather sensor."""

    _attr_has_entity_name = True

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
        # BACKWARDS COMPAT: unique_id HAS domain prefix (asymmetry with weather entity)
        self._attr_unique_id = f"{DOMAIN}_{config_entry_id}_{description.key}"

    @property
    def _current_data(self) -> ObservationDetails | None:
        """Safely get current observation data."""
        if (
            self.coordinator.data
            and (current_list := self.coordinator.data.get("current"))
            and current_list
        ):
            return current_list[0]
        return None

    @property
    def native_value(self) -> Any | None:
        """Return the state of the sensor.

        Does NOT manually round — HA uses suggested_display_precision from the
        entity description for display rounding.
        """
        data = self._current_data
        if data is None:
            return None
        return getattr(data, self.entity_description.key, None)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        data = self._current_data
        if data is None:
            return None
        valid_utc: datetime | None = getattr(data, "valid_time", None)
        if valid_utc:
            local_valid_time = dt_util.as_local(valid_utc)
            return {"last_updated": local_valid_time.isoformat()}
        return None

    @property
    def available(self) -> bool:
        """Return True if entity is available (value is not None)."""
        if not super().available:
            return False
        data = self._current_data
        if data is None:
            return False
        return getattr(data, self.entity_description.key, None) is not None


def _clean_text(text: str) -> str:
    """Clean raw ARSO text for display and TTS.

    - Strips leading/trailing whitespace per line.
    - Collapses multiple blank lines into one.
    - Removes trailing whitespace.
    """
    lines = [line.strip() for line in text.split("\n")]
    # Collapse multiple blank lines
    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                cleaned.append("")
            prev_blank = True
        else:
            cleaned.append(line)
            prev_blank = False
    return "\n".join(cleaned).strip()


def _truncate_at_sentence(text: str, max_len: int = 255) -> str:
    """Truncate text at a sentence boundary within max_len chars."""
    if len(text) <= max_len:
        return text
    # Try to find last sentence end (. ! ?) within limit
    truncated = text[: max_len - 3]
    for sep in (". ", "! ", "? "):
        idx = truncated.rfind(sep)
        if idx > 0:
            return truncated[: idx + 1] + ".."
    # No sentence boundary found, cut at word boundary
    idx = truncated.rfind(" ")
    if idx > 0:
        return truncated[:idx] + "..."
    return truncated + "..."


class ArsoTextSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Text-based sensor for text forecast and bio-weather data.

    HA sensor state is limited to 255 characters. The state contains
    a sentence-boundary truncation. The ``full_text`` attribute always
    contains the complete cleaned text for TTS / automations.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        description: SensorEntityDescription,
        device_info: DeviceInfo,
        config_entry_id: str,
        prefix: str,
    ) -> None:
        """Initialize the text sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_{prefix}_{description.key}"
        )

    def _get_clean_value(self) -> str | None:
        """Get cleaned text from coordinator data."""
        if not self.coordinator.data:
            return None
        value = self.coordinator.data.get(self.entity_description.key)
        if isinstance(value, str):
            return _clean_text(value)
        return value

    @property
    def native_value(self) -> str | None:
        """Return the state (truncated at sentence boundary)."""
        value = self._get_clean_value()
        if not isinstance(value, str):
            return value
        return _truncate_at_sentence(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return full text and update time as attributes.

        ``full_text`` is always present so TTS scripts can reference it
        consistently regardless of text length.
        """
        if not self.coordinator.data:
            return None
        value = self._get_clean_value()
        attrs: dict[str, Any] = {}
        if value:
            attrs["full_text"] = value
        updated = self.coordinator.data.get("updated")
        if updated:
            attrs["last_updated"] = updated
        audio_url = self.coordinator.data.get("audio_url")
        if audio_url:
            attrs["audio_url"] = audio_url
        return attrs if attrs else None

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get(self.entity_description.key) is not None


class ArsoSkiResortSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Sensor for a ski resort showing current conditions.

    State: conditions text + temperature (e.g. "oblačno, 8°C").
    Attributes: full weather details + forecast time slots.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:ski"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        display_name: str,
        xml_key: str,
    ) -> None:
        """Initialize the ski resort sensor."""
        super().__init__(coordinator)
        self._xml_key = xml_key
        self._display_name = display_name
        self._attr_name = f"Ski {display_name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_ski_{xml_key.replace(' ', '_').lower()}"
        )

    def _resort_data(self) -> dict | None:
        """Get data for this resort from coordinator."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._xml_key)

    @property
    def native_value(self) -> str | None:
        """Return compact state: conditions + temp (windchill)."""
        data = self._resort_data()
        if not data:
            return None
        current = data.get("current", {})
        conditions = current.get("conditions", "")
        temp = current.get("temperature")
        windchill = current.get("windchill")
        temp_str = ""
        if temp is not None:
            temp_str = f"{temp}°C"
            if windchill is not None and windchill != temp:
                temp_str += f" (občutek {windchill}°C)"
        if conditions and temp_str:
            return f"{conditions}, {temp_str}"
        if conditions:
            return conditions
        return temp_str or None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return detailed resort weather data."""
        data = self._resort_data()
        if not data:
            return None
        current = data.get("current", {})
        attrs: dict[str, Any] = {
            "altitude": data.get("altitude"),
            "temperature": current.get("temperature"),
            "windchill": current.get("windchill"),
            "humidity": current.get("humidity"),
            "conditions": current.get("conditions"),
            "wind_direction": current.get("wind_direction"),
            "wind_speed_kmh": current.get("wind_speed_kmh"),
            "wind_gust_kmh": current.get("wind_gust_kmh"),
            "precipitation": current.get("precipitation"),
            "weather_phenomena": current.get("weather_phenomena"),
            "thunderstorm": current.get("thunderstorm"),
            "fog": current.get("fog"),
            "visibility_km": current.get("visibility_km"),
            "snow_depth_cm": data.get("snow_depth_cm"),
            "snow_new_cm": data.get("snow_new_cm"),
            "snow_station": data.get("snow_station"),
            "snow_station_altitude": data.get("snow_station_altitude"),
            "valid": current.get("valid"),
            "updated": data.get("updated"),
        }
        # Include next few forecast slots with full data
        forecast = data.get("forecast", [])
        if forecast:
            attrs["forecast"] = [
                {
                    "valid": slot.get("valid"),
                    "conditions": slot.get("conditions"),
                    "temperature": slot.get("temperature"),
                    "windchill": slot.get("windchill"),
                    "wind_direction": slot.get("wind_direction"),
                    "wind_speed_kmh": slot.get("wind_speed_kmh"),
                    "wind_gust_kmh": slot.get("wind_gust_kmh"),
                    "precipitation": slot.get("precipitation"),
                }
                for slot in forecast[:8]  # Next 24h (8 × 3h slots)
            ]
        return attrs

    @property
    def available(self) -> bool:
        """Return True if resort data is available."""
        if not super().available:
            return False
        return self._resort_data() is not None


# Key elevations for individual temperature/wind sensors
_MTN_TEMP_ELEVATIONS = (1500, 2000, 2500, 3000)
_MTN_WIND_ELEVATIONS = (1500, 2000, 2500, 3000)


class _MountainElevationBase(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Base for mountain elevation sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        region_id: str,
        display_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._region_id = region_id
        self._display_name = display_name
        self._attr_device_info = device_info
        self._config_entry_id = config_entry_id

    def _region_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("elevation", {}).get(self._region_id)

    def _current(self) -> dict:
        data = self._region_data()
        if not data:
            return {}
        return data.get("current", {})

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._region_data() is not None


class ArsoMountainOverviewSensor(_MountainElevationBase):
    """Summary sensor for a mountain region.

    State: zero isotherm / snow line.
    Attributes: full current data + forecast.
    """

    _attr_icon = "mdi:image-filter-hdr"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        region_id: str,
        display_name: str,
    ) -> None:
        super().__init__(
            coordinator, device_info, config_entry_id, region_id, display_name
        )
        self._attr_name = f"{display_name}"
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_mtn_elev_"
            f"{region_id.replace('-', '_').lower()}"
        )

    @property
    def native_value(self) -> str | None:
        current = self._current()
        if not current:
            return None
        parts: list[str] = []
        zi = current.get("zero_isotherm_m")
        if zi is not None:
            parts.append(f"0°C: {zi}m")
        sl = current.get("snow_line_m")
        if sl is not None:
            parts.append(f"sneg: {sl}m")
        stab = current.get("stability")
        if stab:
            parts.append(stab)
        return ", ".join(parts) if parts else self._display_name

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._region_data()
        if not data:
            return None
        current = self._current()
        attrs: dict[str, Any] = {
            "region": data.get("region", self._display_name),
            "updated": data.get("updated"),
        }
        if current.get("zero_isotherm_m") is not None:
            attrs["zero_isotherm_m"] = current["zero_isotherm_m"]
        if current.get("snow_line_m") is not None:
            attrs["snow_line_m"] = current["snow_line_m"]
        if current.get("stability"):
            attrs["stability"] = current["stability"]
        # Weather conditions per elevation
        for elev in (2500, 1500):
            val = current.get(f"conditions_{elev}m")
            if val is not None:
                attrs[f"conditions_{elev}m"] = val
        # Temperature, wind, humidity per elevation
        for elev in _MTN_TEMP_ELEVATIONS:
            val = current.get(f"temp_{elev}m")
            if val is not None:
                attrs[f"temp_{elev}m"] = val
            hum = current.get(f"humidity_{elev}m")
            if hum is not None:
                attrs[f"humidity_{elev}m"] = hum
        for elev in _MTN_WIND_ELEVATIONS:
            wind = current.get(f"wind_{elev}m_kmh")
            if wind is not None:
                attrs[f"wind_{elev}m_kmh"] = wind
            wind_dir = current.get(f"wind_{elev}m_dir")
            if wind_dir is not None:
                attrs[f"wind_{elev}m_dir"] = wind_dir
        # Forecast
        forecast = data.get("forecast", [])
        if forecast:
            attrs["forecast"] = forecast[:8]
        return attrs


class ArsoMountainTempSensor(_MountainElevationBase):
    """Temperature sensor for a specific elevation in a mountain region."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        region_id: str,
        display_name: str,
        elevation: int,
    ) -> None:
        super().__init__(
            coordinator, device_info, config_entry_id, region_id, display_name
        )
        self._elevation = elevation
        self._attr_name = f"{display_name} {elevation}m temperatura"
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_mtn_temp_{elevation}_"
            f"{region_id.replace('-', '_').lower()}"
        )
        self._attr_icon = "mdi:thermometer"

    @property
    def native_value(self) -> float | None:
        val = self._current().get(f"temp_{self._elevation}m")
        return val

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        current = self._current()
        attrs: dict[str, Any] = {}
        hum = current.get(f"humidity_{self._elevation}m")
        if hum is not None:
            attrs["humidity"] = hum
        return attrs if attrs else None


class ArsoMountainWindSensor(_MountainElevationBase):
    """Wind speed sensor for a specific elevation in a mountain region."""

    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        region_id: str,
        display_name: str,
        elevation: int,
    ) -> None:
        super().__init__(
            coordinator, device_info, config_entry_id, region_id, display_name
        )
        self._elevation = elevation
        self._attr_name = f"{display_name} {elevation}m veter"
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_mtn_wind_{elevation}_"
            f"{region_id.replace('-', '_').lower()}"
        )
        self._attr_icon = "mdi:weather-windy"

    @property
    def native_value(self) -> float | None:
        return self._current().get(f"wind_{self._elevation}m_kmh")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        current = self._current()
        attrs: dict[str, Any] = {}
        direction = current.get(f"wind_{self._elevation}m_dir")
        if direction is not None:
            attrs["wind_direction"] = direction
        return attrs if attrs else None


# ---------------------------------------------------------------------------
# Agrometeo sensors
# ---------------------------------------------------------------------------


def _format_agro_day(day: dict[str, Any]) -> dict[str, Any]:
    """Format an agrometeo day dict with user-friendly Slovenian keys."""
    result: dict[str, Any] = {}
    if day.get("date"):
        result["datum"] = day["date"]
    if day.get("tklim") is not None:
        result["povprecna_temperatura_C"] = day["tklim"]
    if day.get("tn") is not None:
        result["minimalna_temperatura_C"] = day["tn"]
    if day.get("tx") is not None:
        result["maksimalna_temperatura_C"] = day["tx"]
    if day.get("tn_5_cm") is not None:
        result["min_temperatura_5cm_C"] = day["tn_5_cm"]
    if day.get("tg_5_cm") is not None:
        result["temperatura_tal_5cm_C"] = day["tg_5_cm"]
    if day.get("tg_10_cm") is not None:
        result["temperatura_tal_10cm_C"] = day["tg_10_cm"]
    if day.get("tg_30_cm") is not None:
        result["temperatura_tal_30cm_C"] = day["tg_30_cm"]
    if day.get("tp_24h_acc") is not None:
        result["padavine_24h_mm"] = day["tp_24h_acc"]
    if day.get("sunDur") is not None:
        result["trajanje_sonca_h"] = day["sunDur"]
    if day.get("etp") is not None:
        result["evapotranspiracija_mm"] = day["etp"]
    if day.get("wBal") is not None:
        result["vodna_bilanca_mm"] = day["wBal"]
    if day.get("ffavg_val") is not None:
        result["povprecni_veter_kmh"] = day["ffavg_val"]
    if day.get("ffmax_val") is not None:
        result["max_sunek_vetra_kmh"] = day["ffmax_val"]
    if day.get("thi") is not None:
        result["indeks_temp_vlage"] = day["thi"]
    if day.get("rhavg") is not None:
        result["povprecna_vlaznost_pct"] = day["rhavg"]
    if day.get("sunrise"):
        result["vzhod"] = day["sunrise"]
    if day.get("sunset"):
        result["zahod"] = day["sunset"]
    if day.get("clouds_icon"):
        result["oblacnost"] = day["clouds_icon"]
    if day.get("wwsyn_icon"):
        result["vreme"] = day["wwsyn_icon"]
    return result


class ArsoAgrometeoOverviewSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Overview sensor for an agrometeo station.

    State: summary of soil temp + ETP + water balance.
    Attributes: full observation data + history + forecast.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:sprout"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        station_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._station_name = station_name
        self._attr_name = f"Agrometeo {station_name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_agro_"
            f"{station_name.replace(' ', '_').lower()}"
        )

    def _station_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._station_name)

    @property
    def native_value(self) -> str | None:
        data = self._station_data()
        if not data:
            return None
        current = data.get("current", {})
        parts: list[str] = []
        tg5 = current.get("tg_5_cm")
        if tg5 is not None:
            parts.append(f"Tal 5cm: {tg5}°C")
        tx = current.get("tx")
        if tx is not None:
            parts.append(f"Max: {tx}°C")
        tn = current.get("tn")
        if tn is not None:
            parts.append(f"Min: {tn}°C")
        etp = current.get("etp")
        if etp is not None:
            parts.append(f"ETP: {etp}mm")
        wbal = current.get("wBal")
        if wbal is not None:
            parts.append(f"Bilanca: {wbal}mm")
        return ", ".join(parts) if parts else self._station_name

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._station_data()
        if not data:
            return None
        current = data.get("current", {})
        attrs: dict[str, Any] = {
            "postaja": self._station_name,
            "posodobljeno": data.get("updated"),
        }
        # Build a single chronological timeline: history → today → forecast
        from datetime import date as date_type

        today_str = date_type.today().isoformat()
        dnevi: list[dict[str, Any]] = []
        for day in data.get("history", []):
            entry = _format_agro_day(day)
            entry["tip"] = "meritev"
            dnevi.append(entry)
        current_entry = _format_agro_day(current)
        current_entry["tip"] = "meritev"
        dnevi.append(current_entry)
        for day in data.get("forecast", [])[:10]:
            entry = _format_agro_day(day)
            entry["tip"] = "danes" if entry.get("datum") == today_str else "napoved"
            dnevi.append(entry)
        # Sort by date ascending
        dnevi.sort(key=lambda d: d.get("datum", ""))
        attrs["dnevi"] = dnevi
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._station_data() is not None


class ArsoAgrometeoValueSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Individual agrometeo value sensor (soil temp, ETP, etc.).

    Disabled by default — users enable the ones they need.
    """

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        station_name: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._station_name = station_name
        self.entity_description = description
        self._attr_name = f"{station_name} {description.name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_agro_"
            f"{station_name.replace(' ', '_').lower()}_{description.key}"
        )

    def _station_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._station_name)

    @property
    def native_value(self) -> float | None:
        data = self._station_data()
        if not data:
            return None
        key = self.entity_description.key
        value = data.get("current", {}).get(key)
        if value is None:
            # Fall back to first forecast day (e.g. ETP, wBal are forecast-only)
            forecast = data.get("forecast", [])
            if forecast:
                value = forecast[0].get(key)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._station_data()
        if not data:
            return None
        current = data.get("current", {})
        key = self.entity_description.key
        attrs: dict[str, Any] = {"date": current.get("date")}
        # If value comes from forecast, show that date instead
        if current.get(key) is None:
            forecast = data.get("forecast", [])
            if forecast and forecast[0].get(key) is not None:
                attrs["date"] = forecast[0].get("date")
                attrs["vir"] = "napoved"
        # Include history for this value
        history = data.get("history", [])
        if history:
            attrs["history"] = [
                {"date": d.get("date"), key: d.get(key)}
                for d in history
                if d.get(key) is not None
            ]
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        data = self._station_data()
        if not data:
            return False
        return data.get("current", {}).get(self.entity_description.key) is not None


# ---------------------------------------------------------------------------
# Air quality sensors
# ---------------------------------------------------------------------------


class ArsoAirQualityOverviewSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """European Air Quality Index (EAQI) sensor for a station.

    State: numeric 1-6 (EAQI index).
    Attributes: label, per-pollutant breakdown, all hourly + daily measurements.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:air-filter"
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        station_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._station_name = station_name
        self._attr_name = f"EAQI {station_name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_aq_"
            f"{station_name.replace(' ', '_').replace('-', '_').lower()}"
        )

    def _station_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._station_name)

    @property
    def native_value(self) -> str | None:
        data = self._station_data()
        if not data:
            return None
        eaqi = compute_eaqi(data)
        if not eaqi:
            return None
        return eaqi["label"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._station_data()
        if not data:
            return None
        hourly = data.get("hourly", {})

        attrs: dict[str, Any] = {
            "station": self._station_name,
            "sifra": data.get("sifra"),
            "altitude": data.get("altitude"),
            "datum_od": hourly.get("datum_od"),
            "datum_do": hourly.get("datum_do"),
        }

        # EAQI breakdown
        eaqi = compute_eaqi(data)
        if eaqi:
            attrs["eaqi_index"] = eaqi["index"]
            for pollutant, comp in eaqi["components"].items():
                attrs[f"eaqi_{pollutant}_index"] = comp["index"]
                attrs[f"eaqi_{pollutant}_label"] = comp["label"]
                attrs[f"eaqi_{pollutant}_value"] = comp["value"]

        # Hourly values
        attrs["pm10"] = hourly.get("pm10")
        attrs["pm2.5"] = hourly.get("pm2.5")
        attrs["o3"] = hourly.get("o3")
        attrs["no2"] = hourly.get("no2")
        attrs["so2"] = hourly.get("so2")
        attrs["co"] = hourly.get("co")
        attrs["benzen"] = hourly.get("benzen")
        attrs["nox"] = hourly.get("nox")

        # Daily aggregates
        daily = data.get("daily", {})
        if daily:
            attrs["datum_dnevni"] = daily.get("datum")
            attrs["pm10_dnevna"] = daily.get("pm10_dnevna")
            attrs["pm2.5_dnevna"] = daily.get("pm2.5_dnevna")
            attrs["o3_max_urna"] = daily.get("o3_max_urna")
            attrs["o3_max_8urna"] = daily.get("o3_max_8urna")
            attrs["no2_max_urna"] = daily.get("no2_max_urna")
            attrs["so2_dnevna"] = daily.get("so2_dnevna")
            attrs["so2_max_urna"] = daily.get("so2_max_urna")
            attrs["co_max_8urna"] = daily.get("co_max_8urna")
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._station_data() is not None


class ArsoAirQualityValueSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Individual air quality pollutant sensor (PM10, PM2.5, O3, etc.).

    Disabled by default -- users enable the ones they need.
    """

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        station_name: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self._station_name = station_name
        self.entity_description = description
        self._attr_name = f"{station_name} {description.name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_aq_"
            f"{station_name.replace(' ', '_').replace('-', '_').lower()}"
            f"_{description.key.replace('.', '_')}"
        )

    def _station_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._station_name)

    @property
    def native_value(self) -> float | None:
        data = self._station_data()
        if not data:
            return None
        return data.get("hourly", {}).get(self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._station_data()
        if not data:
            return None
        hourly = data.get("hourly", {})
        attrs: dict[str, Any] = {
            "datum_od": hourly.get("datum_od"),
            "datum_do": hourly.get("datum_do"),
        }
        # Include daily aggregate for this pollutant if available
        daily = data.get("daily", {})
        key = self.entity_description.key
        # Map hourly keys to their daily equivalents
        daily_map = {
            "pm10": "pm10_dnevna",
            "pm2.5": "pm2.5_dnevna",
            "o3": "o3_max_urna",
            "no2": "no2_max_urna",
            "so2": "so2_dnevna",
            "co": "co_max_8urna",
        }
        daily_key = daily_map.get(key)
        if daily_key and daily.get(daily_key) is not None:
            attrs[daily_key] = daily[daily_key]
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        data = self._station_data()
        if not data:
            return False
        return data.get("hourly", {}).get(self.entity_description.key) is not None


# ---------------------------------------------------------------------------
# UTCI sensors
# ---------------------------------------------------------------------------


class ArsoUtciSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """UTCI (Universal Thermal Climate Index) sensor for a station.

    State: current UTCI value in °C.
    Attributes: stress category, min/max over forecast period, forecast data.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:thermometer-lines"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        station_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._station_name = station_name
        self._attr_name = f"UTCI {station_name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_utci_"
            f"{station_name.replace(' ', '_').lower()}"
        )

    def _station_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._station_name)

    @property
    def native_value(self) -> float | None:
        data = self._station_data()
        if not data:
            return None
        current = data.get("current", {})
        return current.get("utci")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._station_data()
        if not data:
            return None
        current = data.get("current", {})
        attrs: dict[str, Any] = {
            "station": self._station_name,
            "category": current.get("category"),
            "time": current.get("time"),
            "min_utci": data.get("min_utci"),
            "max_utci": data.get("max_utci"),
        }
        # Include forecast (next 24h)
        forecast = data.get("forecast", [])
        if forecast:
            attrs["forecast"] = forecast[:24]
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._station_data() is not None


# ---------------------------------------------------------------------------
# Weather warnings sensor
# ---------------------------------------------------------------------------


class ArsoWarningsOverviewSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Overview sensor for weather warnings.

    State: "Ni opozoril" when no active warnings (level >= 2),
           or summary like "Veter (oranžna), Dež (rumena)".
    Attributes: region, full warning details, updated timestamp.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-outline"

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        location_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._location_name = location_name
        self._attr_name = "Vremenska opozorila"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_warnings_overview"
        )

    def _active_warnings(self) -> list[dict]:
        """Get warnings with level >= 2 (meaningful alerts)."""
        if not self.coordinator.data:
            return []
        return [
            w for w in self.coordinator.data.get("warnings", [])
            if w.get("level", 0) >= 2
        ]

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        active = self._active_warnings()
        if not active:
            return "Ni opozoril"
        parts = [
            f"{w['type_name']} ({w.get('level_color', '')})"
            for w in active
        ]
        return ", ".join(parts)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        data = self.coordinator.data
        active = self._active_warnings()
        attrs: dict[str, Any] = {
            "regija": data.get("region_name", ""),
            "regija_id": data.get("region"),
            "posodobljeno": data.get("updated"),
            "stevilo_opozoril": len(active),
        }
        if active:
            attrs["opozorila"] = [
                {
                    "tip": w.get("type"),
                    "tip_ime": w.get("type_name"),
                    "stopnja": w.get("level"),
                    "barva": w.get("level_color"),
                    "opis_stopnje": w.get("level_text"),
                    "naslov": w.get("title"),
                    "opis": w.get("description", ""),
                    "navodila": w.get("instruction", ""),
                    "veljavnost_od": w.get("onset"),
                    "veljavnost_do": w.get("expires"),
                    "posodobljeno": w.get("updated"),
                }
                for w in active
            ]
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self.coordinator.data is not None


# ---------------------------------------------------------------------------
# Avalanche bulletin sensors
# ---------------------------------------------------------------------------


class ArsoAvalancheSensor(
    CoordinatorEntity[DataUpdateCoordinator], SensorEntity
):
    """Avalanche danger sensor for a Slovenian alpine region.

    State: danger label with level, e.g. "Zmerna (2)".
    Attributes: danger ratings by elevation, avalanche problems, text forecasts.
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:landslide"
    _attr_attribution = "Vir podatkov: EAWS / Agencija RS za okolje"

    _INFO_URL = (
        "https://meteo.arso.gov.si/met/sl/weather/bulletin/mountain/avalanche/"
    )
    _DANGER_SCALE = {
        1: "Majhna — snežna odeja je dobro povezana in stabilna",
        2: "Zmerna — na nekaterih strmih pobočjih le zmerno povezana",
        3: "Znatna — na mnogih strmih pobočjih zmerno do slabo povezana",
        4: "Velika — na večini strmih pobočij slabo povezana",
        5: "Zelo velika — splošno zelo nestabilna, številni spontani plazovi",
    }

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device_info: DeviceInfo,
        config_entry_id: str,
        region_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._region_name = region_name
        self._attr_name = f"Plazovi {region_name}"
        self._attr_device_info = device_info
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry_id}_avalanche_"
            f"{region_name.replace(' ', '_').lower()}"
        )

    def _region_data(self) -> dict | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._region_name)

    @property
    def native_value(self) -> str | None:
        data = self._region_data()
        if not data:
            return None
        level = data.get("max_danger_rating", 0)
        label = data.get("max_danger_label", "—")
        if level == 0:
            return "Ni podatkov"
        return f"{label} ({level})"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self._region_data()
        if not data:
            return None
        level = data.get("max_danger_rating", 0)
        attrs: dict[str, Any] = {
            "regija": self._region_name,
            "regija_id": data.get("region_id"),
            "nevarnost_visoko": data.get("danger_rating_high"),
            "nevarnost_nizko": data.get("danger_rating_low"),
            "oznaka_visoko": data.get("danger_label_high"),
            "oznaka_nizko": data.get("danger_label_low"),
            "meja_nadmorske_visine": data.get("elevation_boundary"),
            "opis_stopnje": self._DANGER_SCALE.get(level, ""),
            "problemi": [
                {
                    "tip": p.get("type_label"),
                    "lege": p.get("aspects"),
                    "spodnja_meja": p.get("elevation_lower_bound"),
                    "zgornja_meja": p.get("elevation_upper_bound"),
                    "obdobje": p.get("valid_time_period"),
                }
                for p in data.get("problems", [])
            ],
            "povzetek": data.get("highlights", ""),
            "komentar_aktivnosti": data.get("activity_comment", ""),
            "komentar_snezne_odeje": data.get("snowpack_comment", ""),
            "komentar_vremena": data.get("weather_comment", ""),
            "tendenca": data.get("tendency", ""),
            "tendenca_tip": data.get("tendency_type", ""),
            "cas_objave": data.get("publication_time", ""),
            "veljavnost_od": data.get("valid_start", ""),
            "veljavnost_do": data.get("valid_end", ""),
            "razlaga_lestvice": self._INFO_URL,
        }
        return attrs

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return self._region_data() is not None
