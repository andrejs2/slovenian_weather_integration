from typing import Optional, Any, Type, Union
from datetime import datetime, timezone # Added timezone
from pydantic import BaseModel, Field, field_validator, computed_field, ConfigDict
from .weather_map import CLOUD_CONDITION_MAP, WIND_DIRECTION_MAP


# Helper function to convert empty strings or non-numeric values to None for numeric fields
def empty_string_to_none(value: Any) -> Optional[Any]:
    if value == "" or value is None:
        return None
    # Keep existing value if it's not an empty string
    return value


# ==============================================================================
# Base Class for Timeline Entries
# ==============================================================================


class BaseTimelineEntry(BaseModel):
    """Base model containing common fields found in most timeline entries
    (observations and forecasts).
    """

    model_config = ConfigDict(
        populate_by_name=True,
        validate_by_name=True, # Changed from validate_by_alias for Pydantic v2.11+
        # validate_by_alias=True, # Kept for compatibility if needed, but validate_by_name is preferred
        extra="ignore",
    )

    valid_time: Optional[datetime] = Field( # Made Optional to handle cases where it might be missing initially
        default=None,
        alias="valid",
        description="The timestamp (UTC) for which this data point is valid.",
        examples=["2025-04-27T18:00:00+00:00"],
    )
    temperature: Optional[float] = Field(
        default=None, alias="t", description="Air temperature.", examples=["15", "19"]
    )
    relative_humidity_percent: Optional[int] = Field(
        default=None,
        alias="rh",
        description="Relative humidity percentage.",
        examples=["50", "46"],
    )
    mean_sea_level_pressure_hpa: Optional[float] = Field( # Changed to float for more precision
        default=None,
        alias="msl",
        description="Mean sea level air pressure in hectopascals (hPa).",
        examples=["1024.5", "1023.0"],
    )
    wind_speed_kmh: Optional[float] = Field( # Changed to float
        default=None,
        alias="ff_val",
        description="Average wind speed in kilometers per hour (km/h).",
        examples=["5.5", "8.0"],
    )
    wind_direction_text: Optional[str] = Field(
        default=None,
        alias="dd_shortText",
        description="Textual representation of the wind direction (compass points).",
        examples=["JV", "J", "SZ"],
    )
    max_wind_gust_kmh: Optional[float] = Field( # Changed to float
        default=None,
        alias="ffmax_val",
        description="Maximum wind gust speed in kilometers per hour (km/h). Often empty.",
        examples=["", "51.3"],
    )
    cloud_cover_text: Optional[str] = Field(
        default=None,
        alias="clouds_shortText",
        description="Textual description of cloud cover.",
        examples=[
            "jasno",
            "delno oblačno",
            "pretežno oblačno",
            "oblačno",
        ],
    )
    weather_phenomenon_text: Optional[str] = Field(
        default=None,
        alias="wwsyn_shortText",
        description="Textual description of the significant weather phenomenon.",
        examples=[
            "",
            "možnost neviht",
            "plohe",
            "dež",
        ],
    )
    weather_phenomenon_icon: Optional[str] = Field(
        default=None,
        alias="wwsyn_icon",
        description="Icon name representing the weather phenomenon.",
        examples=[
            "",
            "modTSRA",
            "lightRA",
            "modRA",
        ],
    )
    combined_cloud_weather_icon: Optional[str] = Field(
        default=None,
        alias="clouds_icon_wwsyn_icon",
        description="Combined icon name representing both cloud cover and weather phenomenon.",
        examples=[
            "clear_day",
            "partCloudy_day",
            "prevCloudy_day",
            "clear_night",
            "overcast_lightRA_day",
        ],
    )
    combined_cloud_weather_text: Optional[str] = Field(
        default=None,
        alias="clouds_shortText_wwsyn_shortText",
        description="Combined textual description of cloud cover and weather phenomenon.",
        examples=[
            "jasno",
            "delno oblačno",
            "možnost neviht",
            "plohe",
        ],
    )
    cloud_base_text: Optional[str] = Field(
        default=None,
        alias="cloudBase_shortText",
        description="Textual description of the height of the cloud base.",
        examples=["", "nizka", "srednja", "visoka"],
    )
    time_minutes_from_midnight: Optional[int] = Field(
        default=None,
        alias="time",
        description="Time represented as minutes from midnight for the *start* of the interval or the observation time.",
        examples=["1200", "1380", "840"],
    )

    @field_validator("*", mode="before")
    @classmethod
    def replace_empty_string_with_none(cls, v: Any) -> Optional[Any]:
        return empty_string_to_none(v)

    @field_validator(
        "wind_direction_text",
        mode="after", # Changed from 'before' to 'after' to process the value after it's set
    )
    @classmethod
    def remap_cardinal(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return WIND_DIRECTION_MAP.get(value.upper(), value) # Added .upper() for robustness

    @field_validator('valid_time', mode='before')
    @classmethod
    def ensure_timezone_utc(cls, v: Any) -> Optional[datetime]:
        if v is None:
            return None
        if isinstance(v, str):
            try:
                # Attempt to parse with timezone first
                dt = datetime.fromisoformat(v)
                if dt.tzinfo is None: # If no timezone, assume UTC as per ARSO API docs
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc) # Convert to UTC if it has other timezone
            except ValueError:
                # Handle cases where fromisoformat might fail for some string formats
                # This part might need adjustment based on actual string formats encountered
                return None # Or raise error, or try other parsing
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        return v


    @computed_field
    @property
    def home_assistant_weather_condition(self) -> Optional[str]:
        """
        Calculates a Home Assistant weather condition string based on available text and icon fields,
        checking against CLOUD_CONDITION_MAP in order of precedence.
        Returns the first match found, or "unknown" if no match.
        """
        fields_to_check = [
            self.combined_cloud_weather_icon, # Prioritize combined icon
            self.combined_cloud_weather_text,
            self.weather_phenomenon_icon, # Then specific phenomenon icon
            self.weather_phenomenon_text,
            self.cloud_cover_text,
        ]

        for field_value in fields_to_check:
            if field_value:
                condition = CLOUD_CONDITION_MAP.get(str(field_value).lower().strip()) # Ensure string and strip
                if condition:
                    return condition

        return "unknown"


# ==============================================================================
# Observation Specific Model
# ==============================================================================


class ObservationTimelineEntry(BaseTimelineEntry):
    """
    Represents a single observation data point in the timeline from the basic ARSO API.
    Inherits common fields from BaseTimelineEntry.
    """
    pass


# ==============================================================================
# Forecast Specific Models
# ==============================================================================


class Forecast1hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 1-hour forecast data point in the timeline.
    """
    accumulated_precipitation_mm: Optional[float] = Field(
        default=None,
        alias="tp_acc",
        description="Total accumulated precipitation (rain, melted snow, etc.) during the interval, in millimeters (mm).",
    )
    accumulated_snow_mm: Optional[float] = Field(
        default=None,
        alias="sn_acc",
        description="Accumulated snowfall (water equivalent) during the interval, in millimeters (mm).",
    )


class Forecast3hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 3-hour forecast data point in the timeline.
    """
    accumulated_precipitation_mm: Optional[float] = Field(
        default=None,
        alias="tp_acc",
        description="Total accumulated precipitation (rain, melted snow, etc.) during the interval, in millimeters (mm).",
    )
    accumulated_snow_mm: Optional[float] = Field(
        default=None,
        alias="sn_acc",
        description="Accumulated snowfall (water equivalent) during the interval, in millimeters (mm).",
    )


class Forecast6hTimelineEntry(BaseTimelineEntry): # Not currently used by client but defined for completeness
    """
    Represents a 6-hour forecast data point in the timeline.
    """
    accumulated_precipitation_mm: Optional[float] = Field(
        default=None,
        alias="tp_acc",
        description="Total accumulated precipitation (rain, melted snow, etc.) during the interval, in millimeters (mm).",
    )
    accumulated_snow_mm: Optional[float] = Field(
        default=None,
        alias="sn_acc",
        description="Accumulated snowfall (water equivalent) during the interval, in millimeters (mm).",
    )


class Forecast24hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 24-hour summary forecast data point in the timeline.
    """
    min_temperature_forecast: Optional[float] = Field( # Changed to float
        default=None,
        alias="tnsyn",
        description="Forecasted minimum temperature for the 24-hour period.",
    )
    # 'temperature' (max temp) is inherited from BaseTimelineEntry, but ARSO uses 'txsyn' for 24h max
    # We override it here to ensure correct alias and type
    temperature: Optional[float] = Field( # Changed to float, overrides BaseTimelineEntry.temperature
        default=None,
        alias="txsyn",
        description="Forecasted maximum temperature for the 24-hour period.",
    )
    accumulated_precipitation_24h_mm: Optional[float] = Field(
        default=None,
        alias="tp_24h_acc",
        description="Total accumulated precipitation over the 24-hour period, in millimeters (mm).",
    )
    # NEW: Added field for daily UV index forecast
    uv_index: Optional[float] = Field(
        default=None,
        description="Forecasted UV index for the day (from Temis.nl)."
    )


class ObservationDetails(BaseTimelineEntry):
    """
    Represents observations from primary ARSO stations which includes detailed measurements.
    """
    interval_minutes: Optional[int] = Field(
        default=None,
        alias="interval",
        description="The interval (in minutes) over which averages/max/min are calculated, ending at the valid_time.",
    )
    dew_point: Optional[float] = Field(default=None, alias="td", description="Dew point temperature (°C)")
    temperature_average: Optional[float] = Field(default=None, alias="tavg")
    temperature_max_interval: Optional[float] = Field(default=None, alias="tx")
    temperature_min_interval: Optional[float] = Field(default=None, alias="tn")
    relative_humidity_average: Optional[int] = Field(default=None, alias="rhavg")
    wind_direction_degrees: Optional[int] = Field(default=None, alias="dd_val")
    wind_direction_icon: Optional[str] = Field(default=None, alias="dd_icon")
    wind_direction_average_degrees: Optional[int] = Field(default=None, alias="ddavg_val")
    wind_direction_average_text: Optional[str] = Field(default=None, alias="ddavg_shortText")
    wind_direction_average_long_text: Optional[str] = Field(default=None, alias="ddavg_longText")
    wind_direction_average_icon: Optional[str] = Field(default=None, alias="ddavg_icon")
    wind_direction_max_gust_degrees: Optional[int] = Field(default=None, alias="ddmax_val")
    wind_direction_max_gust_text: Optional[str] = Field(default=None, alias="ddmax_shortText")
    wind_direction_max_gust_icon: Optional[str] = Field(default=None, alias="ddmax_icon")
    wind_speed_average_kmh: Optional[float] = Field(default=None, alias="ffavg_val") # Changed to float
    wind_speed_average_icon: Optional[str] = Field(default=None, alias="ffavg_icon")
    max_wind_gust_icon: Optional[str] = Field(default=None, alias="ffmax_icon")
    mean_sea_level_pressure_average_hpa: Optional[float] = Field(default=None, alias="mslavg")
    station_pressure_hpa: Optional[float] = Field(default=None, alias="p")
    station_pressure_average_hpa: Optional[float] = Field(default=None, alias="pavg")
    precipitation_accumulated_mm: Optional[float] = Field(default=None, alias="tp_acc")
    snow_depth_cm: Optional[float] = Field(default=None, alias="snow")
    precipitation_1h_accumulated_mm: Optional[float] = Field(default=None, alias="tp_1h_acc")
    precipitation_12h_accumulated_mm: Optional[float] = Field(default=None, alias="tp_12h_acc")
    precipitation_24h_accumulated_mm: Optional[float] = Field(default=None, alias="tp_24h_acc") # This is different from Forecast24hTimelineEntry.accumulated_precipitation_24h_mm
    water_temperature: Optional[float] = Field(default=None, alias="tw")
    global_solar_radiation_wm2: Optional[int] = Field(default=None, alias="gSunRad")
    global_solar_radiation_average_wm2: Optional[int] = Field(default=None, alias="gSunRadavg")
    diffuse_solar_radiation_wm2: Optional[int] = Field(default=None, alias="diffSunRad")
    diffuse_solar_radiation_average_wm2: Optional[int] = Field(default=None, alias="diffSunRadavg")
    visibility_km: Optional[Union[int, float]] = Field(default=None, alias="vis_val")
    temperature_at_5cm: Optional[float] = Field(default=None, alias="t_5_cm")
    temperature_average_at_5cm: Optional[float] = Field(default=None, alias="tavg_5_cm")
    ground_temperature_at_5cm: Optional[float] = Field(default=None, alias="tg_5_cm")
    ground_temperature_average_at_5cm: Optional[float] = Field(default=None, alias="tgavg_5_cm")
    ground_temperature_at_10cm: Optional[float] = Field(default=None, alias="tg_10_cm")
    ground_temperature_average_at_10cm: Optional[float] = Field(default=None, alias="tgavg_10_cm")
    ground_temperature_at_20cm: Optional[float] = Field(default=None, alias="tg_20_cm")
    ground_temperature_average_at_20cm: Optional[float] = Field(default=None, alias="tgavg_20_cm")
    ground_temperature_at_30cm: Optional[float] = Field(default=None, alias="tg_30_cm")
    ground_temperature_average_at_30cm: Optional[float] = Field(default=None, alias="tgavg_30_cm")
    ground_temperature_at_50cm: Optional[float] = Field(default=None, alias="tg_50_cm")
    ground_temperature_average_at_50cm: Optional[float] = Field(default=None, alias="tgavg_50_cm")

    # NEW: Added field for current UV index
    current_uv_index: Optional[float] = Field(
        default=None,
        description="Current UV index (from Temis.nl)."
    )

    @field_validator( # Ensure this validator also applies to new fields if they come from ARSO with Slovenian text
        "wind_direction_text",
        "wind_direction_icon", # This might not need remapping if it's already a standard icon name
        "wind_direction_average_text",
        "wind_direction_average_icon", # Same as above
        "wind_direction_max_gust_text",
        "wind_direction_max_gust_icon", # Same as above
        mode="after",
    )
    @classmethod
    def remap_detailed_cardinal(cls, value: Optional[str]) -> Optional[str]: # Renamed to avoid Pydantic warning if same name as in Base
        if value is None:
            return None
        # Only remap if it's likely a Slovenian cardinal direction (e.g., 1-2 chars or specific known values)
        # This is a simple heuristic; adjust if needed.
        if value in WIND_DIRECTION_MAP:
             return WIND_DIRECTION_MAP.get(value.upper(), value)
        return value


    @computed_field
    @property
    def precipitation_rate(self) -> Optional[float]:
        """
        Precipitation is provided as mm in 10 minutes (if interval_minutes is 10).
        This converts it to mm/h.
        Assumes precipitation_accumulated_mm is for the 'interval_minutes'.
        """
        if self.precipitation_accumulated_mm is None or self.interval_minutes is None or self.interval_minutes == 0:
            return None
        try:
            rate = (float(self.precipitation_accumulated_mm) / float(self.interval_minutes)) * 60
            return round(rate, 2)
        except (ValueError, TypeError):
            return None

# ==============================================================================
# UV Index Specific Models (for internal use in client.py before merging)
# ==============================================================================

class UVForecastDataPoint(BaseModel):
    """
    Represents a single data point for UV forecast from Temis.nl,
    used internally by the client before merging into Forecast24hTimelineEntry.
    """
    model_config = ConfigDict(extra="ignore")

    valid_time: datetime # Date of the forecast
    uv_index: Optional[float] = Field(default=None, alias="uv_index_forecast") # Alias matches client.py logic

    @field_validator('valid_time', mode='before')
    @classmethod
    def ensure_timezone_uv(cls, v: Any) -> datetime: # Type hint changed to datetime
        if isinstance(v, str):
            dt = datetime.fromisoformat(v) # Assuming ISO format from client
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc) # Assume UTC if not specified
            return dt.astimezone(timezone.utc)
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        raise ValueError("Invalid datetime type for UVForecastDataPoint valid_time")


# ==============================================================================
# Mapping and Merging
# ==============================================================================

MODEL_MAPPING: dict[str, Type[BaseTimelineEntry]] = { # Type hint changed
    "observation": ObservationTimelineEntry, # Added for basic observation parsing
    "forecast1h": Forecast1hTimelineEntry,
    "forecast3h": Forecast3hTimelineEntry,
    "forecast6h": Forecast6hTimelineEntry, # Although not used by client, keep for consistency
    "forecast24h": Forecast24hTimelineEntry,
}


def merge_observation_data(
    base_observation: ObservationTimelineEntry, detailed_observation_data: dict
) -> ObservationDetails:
    """
    Merges data from a base ObservationTimelineEntry (from general ARSO API)
    with more detailed observation data (typically a dict from primary station JSON)
    into a new ObservationDetails instance.

    It prioritizes non-None values from the `detailed_observation_data` for shared fields.
    """
    # Start with the data from the base observation model
    merged_data = base_observation.model_dump(by_alias=False, exclude_none=False) # Keep Nones from base

    # Update with detailed data, prioritizing non-None values from it
    for key, value in detailed_observation_data.items():
        if value is not None: # Only update if detail value is not None
            merged_data[key] = value
        elif key not in merged_data: # If key is new and value is None, add it
             merged_data[key] = None


    # Ensure all required fields for ObservationDetails are present, even if None
    # Pydantic will handle missing fields with defaults or raise errors if no default
    final_details = ObservationDetails.model_validate(merged_data)
    return final_details
