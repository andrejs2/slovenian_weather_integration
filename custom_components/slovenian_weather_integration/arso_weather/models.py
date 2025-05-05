from typing import Optional, Any, Type, Union
from datetime import datetime
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
        populate_by_name=True,  # Allow using field names for population, relevant for upto including pydantic v2.10
        validate_by_name=True,  # Allow using field names for population, relevant for pydantic v2.11 and later
        validate_by_alias=True,  # Allow using aliases for population, relevant for pydantic v2.11 and later
        extra="ignore",  # Ignore extra fields from the API response
    )

    valid_time: datetime = Field(
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
    mean_sea_level_pressure_hpa: Optional[int] = Field(
        default=None,
        alias="msl",
        description="Mean sea level air pressure in hectopascals (hPa).",
        examples=["1024", "1023"],
    )
    wind_speed_kmh: Optional[int] = Field(
        default=None,
        alias="ff_val",
        description="Average wind speed in kilometers per hour (km/h).",
        examples=["5", "8"],
    )
    wind_direction_text: Optional[str] = Field(
        default=None,
        alias="dd_shortText",
        description="Textual representation of the wind direction (compass points).",
        examples=["JV", "J", "SZ"],  # SE, S, NW
    )
    max_wind_gust_kmh: Optional[int] = Field(
        default=None,
        alias="ffmax_val",
        description="Maximum wind gust speed in kilometers per hour (km/h). Often empty.",
        examples=["", "51"],
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
        ],  # clear, partly cloudy, mostly cloudy, overcast
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
        ],  # "", possibility of thunderstorms, showers, rain
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
        ],  # "", moderate Thunderstorm/Rain, light Rain, moderate Rain
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
        ],  # clear, partly cloudy, possibility of thunderstorms, showers
    )
    cloud_base_text: Optional[str] = Field(
        default=None,
        alias="cloudBase_shortText",
        description="Textual description of the height of the cloud base.",
        examples=["", "nizka", "srednja", "visoka"],  # "", low, medium, high
    )
    time_minutes_from_midnight: Optional[int] = Field(
        default=None,
        alias="time",
        description="Time represented as minutes from midnight for the *start* of the interval or the observation time.",
        examples=["1200", "1380", "840"],  # 1200 = 20:00, 1380 = 23:00, 840 = 14:00
    )

    @field_validator("*", mode="before")
    @classmethod
    def replace_empty_string_with_none(cls, v):
        return empty_string_to_none(v)

    @field_validator(
        "wind_direction_text",
        mode="after",
    )
    @classmethod
    def remap_cardinal(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return WIND_DIRECTION_MAP.get(value, value)

    @computed_field
    @property
    def home_assistant_weather_condition(self) -> Optional[str]:
        """
        Calculates a Home Assistant weather condition string based on available text and icon fields,
        checking against CLOUD_CONDITION_MAP in order of precedence.
        Returns the first match found, or "unknown" if no match.
        """
        fields_to_check = [
            self.combined_cloud_weather_text,
            self.combined_cloud_weather_icon,
            self.weather_phenomenon_text,
            self.weather_phenomenon_icon,
            self.cloud_cover_text,
        ]

        for field_value in fields_to_check:
            if field_value:  # Check if the field has a non-None/non-empty value
                # Perform case-insensitive lookup
                condition = CLOUD_CONDITION_MAP.get(field_value.lower())
                if condition:
                    return condition  # Return the first match found

        # If no match is found after checking all fields
        return "unknown"


# ==============================================================================
# Observation Specific Model
# ==============================================================================


class ObservationTimelineEntry(BaseTimelineEntry):
    """
    Represents a single observation data point in the timeline.
    Inherits common fields from BaseTimelineEntry.
    Observations typically lack forecast-specific fields like accumulation or interval.
    """

    # No specific fields for observation timeline entries in the provided example,
    # beyond what's in BaseTimelineEntry. If others exist, add them here.
    pass


# ==============================================================================
# Forecast Specific Models (Intermediate and Final)
# ==============================================================================


class Forecast1hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 1-hour forecast data point in the timeline.
    Inherits fields from ForecastTimelineEntry.
    Interval is typically 60 minutes.
    """

    accumulated_precipitation_mm: Optional[float] = Field(
        default=None,
        alias="tp_acc",
        description="Total accumulated precipitation (rain, melted snow, etc.) during the interval, in millimeters (mm).",
        examples=["0.0", "4.5", "19.9"],
    )
    accumulated_snow_mm: Optional[float] = Field(
        default=None,
        alias="sn_acc",
        description="Accumulated snowfall (water equivalent) during the interval, in millimeters (mm).",
        examples=["0.0"],
    )


class Forecast3hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 3-hour forecast data point in the timeline.
    Inherits fields from ForecastTimelineEntry.
    Interval is typically 180 minutes.
    """

    accumulated_precipitation_mm: Optional[float] = Field(
        default=None,
        alias="tp_acc",
        description="Total accumulated precipitation (rain, melted snow, etc.) during the interval, in millimeters (mm).",
        examples=["0.0", "4.5", "19.9"],
    )
    accumulated_snow_mm: Optional[float] = Field(
        default=None,
        alias="sn_acc",
        description="Accumulated snowfall (water equivalent) during the interval, in millimeters (mm).",
        examples=["0.0"],
    )


class Forecast6hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 6-hour forecast data point in the timeline.
    Inherits fields from ForecastTimelineEntry.
    Interval is typically 360 minutes.
    """

    accumulated_precipitation_mm: Optional[float] = Field(
        default=None,
        alias="tp_acc",
        description="Total accumulated precipitation (rain, melted snow, etc.) during the interval, in millimeters (mm).",
        examples=["0.0", "4.5", "19.9"],
    )
    accumulated_snow_mm: Optional[float] = Field(
        default=None,
        alias="sn_acc",
        description="Accumulated snowfall (water equivalent) during the interval, in millimeters (mm).",
        examples=["0.0"],
    )


class Forecast24hTimelineEntry(BaseTimelineEntry):
    """
    Represents a 24-hour summary forecast data point in the timeline.
    Inherits common fields from BaseTimelineEntry but has unique daily fields
    instead of short-term accumulation.
    Interval is typically 1440 minutes.
    """

    min_temperature_forecast: Optional[int] = Field(
        default=None,
        alias="tnsyn",
        description="Forecasted minimum temperature for the 24-hour period.",
        examples=["8", "7", "11"],
    )
    temperature: Optional[int] = (
        Field(  # overrides BaseTimelineEntry temperature, which is missing in 24h data
            default=None,
            alias="txsyn",
            description="Forecasted maximum temperature for the 24-hour period.",
            examples=["18", "21", "24"],
        )
    )
    accumulated_precipitation_24h_mm: Optional[float] = Field(
        default=None,
        alias="tp_24h_acc",
        description="Total accumulated precipitation over the 24-hour period, in millimeters (mm).",
        examples=["0.1", "0", "12.3"],
    )


class ObservationDetails(BaseTimelineEntry):  # Inherits from BaseTimelineEntry
    """
    Represents observations from primary ARSO stations which includes detailed measurements
    for a specific time point. Inherits common fields from BaseTimelineEntry
    and adds more specific measurements like averages, ground temperatures, etc.
    """

    interval_minutes: Optional[int] = Field(
        default=None,
        alias="interval",
        description="The interval (in minutes) over which averages/max/min are calculated, ending at the valid_time.",
        examples=["10"],
    )
    dew_point: Optional[float] = Field(
        default=None,
        alias="td",
        description="Dew point temperature (°C)",
        examples=["6.9"],
    )
    temperature_average: Optional[float] = Field(
        default=None,
        alias="tavg",
        description="Povprečna temperatura v časovnem intervalu (°C)",
        examples=["17.4"],
    )
    temperature_max_interval: Optional[float] = Field(
        default=None,
        alias="tx",
        description="Maksimalna temperatura v časovnem intervalu (°C)",
        examples=[""],
    )
    temperature_min_interval: Optional[float] = Field(
        default=None,
        alias="tn",
        description="Minimalna temperatura v časovnem intervalu (°C)",
        examples=[""],
    )
    relative_humidity_average: Optional[int] = Field(
        default=None,
        alias="rhavg",
        description="Povprečna relativna vlažnost v časovnem intervalu (%)",
        examples=["52"],
    )
    wind_direction_degrees: Optional[int] = Field(
        default=None, alias="dd_val", description="Smer vetra (°)", examples=["112"]
    )
    # wind_direction_text (dd_shortText) is inherited
    wind_direction_icon: Optional[str] = Field(
        default=None, alias="dd_icon", description="Smer vetra (ikona)", examples=["E"]
    )
    wind_direction_average_degrees: Optional[int] = Field(
        default=None,
        alias="ddavg_val",
        description="Povprečna smer vetra v intervalu (°)",
        examples=["112"],
    )
    wind_direction_average_text: Optional[str] = Field(
        default=None,
        alias="ddavg_shortText",
        description="Povprečna smer vetra v intervalu (tekst)",
        examples=["V"],
    )
    wind_direction_average_long_text: Optional[str] = Field(
        default=None,
        alias="ddavg_longText",
        description="Povprečna smer vetra v intervalu (opisno)",
        examples=["vzhodnik"],
    )
    wind_direction_average_icon: Optional[str] = Field(
        default=None,
        alias="ddavg_icon",
        description="Povprečna smer vetra v intervalu (ikona)",
        examples=["E"],
    )
    wind_direction_max_gust_degrees: Optional[int] = Field(
        default=None,
        alias="ddmax_val",
        description="Smer najmočnejšega sunka vetra v intervalu (°)",
        examples=["113"],
    )
    wind_direction_max_gust_text: Optional[str] = Field(
        default=None,
        alias="ddmax_shortText",
        description="Smer najmočnejšega sunka vetra v intervalu (tekst)",
        examples=[""],
    )
    wind_direction_max_gust_icon: Optional[str] = Field(
        default=None,
        alias="ddmax_icon",
        description="Smer najmočnejšega sunka vetra v intervalu (ikona)",
        examples=[""],
    )
    wind_speed_average_kmh: Optional[int] = Field(
        default=None,
        alias="ffavg_val",
        description="Povprečna hitrost vetra v časovnem intervalu (km/h)",
        examples=["14"],
    )
    wind_speed_average_icon: Optional[str] = Field(
        default=None,
        alias="ffavg_icon",
        description="Povprečna hitrost vetra v časovnem intervalu (ikona)",
        examples=["light"],
    )
    # max_wind_gust_kmh (ffmax_val) is inherited
    max_wind_gust_icon: Optional[str] = Field(
        default=None,
        alias="ffmax_icon",
        description="Maksimalna hitrost vetra v časovnem intervalu (ikona)",
        examples=["mod"],
    )
    # mean_sea_level_pressure_hpa (msl) is inherited
    mean_sea_level_pressure_average_hpa: Optional[float] = Field(
        default=None,
        alias="mslavg",
        description="Povprečni zračni tlak reduciran na morski nivo v intervalu (hPa)",
        examples=["1022.6"],
    )
    station_pressure_hpa: Optional[float] = Field(
        default=None,
        alias="p",
        description="Zračni tlak na postaji (hPa)",
        examples=["977.9"],
    )
    station_pressure_average_hpa: Optional[float] = Field(
        default=None,
        alias="pavg",
        description="Povprečni zračni tlak na postaji v intervalu (hPa)",
        examples=["977.9"],
    )
    precipitation_accumulated_mm: Optional[float] = Field(
        default=None, alias="tp_acc", description="Padavine (mm)", examples=["0"]
    )
    snow_depth_cm: Optional[float] = Field(
        default=None,
        alias="snow",
        description="Višina snežne odeje (cm)",
        examples=["0"],
    )
    precipitation_1h_accumulated_mm: Optional[float] = Field(
        default=None,
        alias="tp_1h_acc",
        description="1-urne padavine (mm)",
        examples=[""],
    )
    precipitation_12h_accumulated_mm: Optional[float] = Field(
        default=None,
        alias="tp_12h_acc",
        description="Vsota padavin (od 6 oz. 18 UTC dalje) (mm)",
        examples=["0"],
    )
    precipitation_24h_accumulated_mm: Optional[float] = Field(
        default=None,
        alias="tp_24h_acc",
        description="24-urna vsota padavin (mm)",
        examples=[""],
    )
    water_temperature: Optional[float] = Field(
        default=None, alias="tw", description="Temperatura vode (°C)", examples=[""]
    )
    global_solar_radiation_wm2: Optional[int] = Field(
        default=None,
        alias="gSunRad",
        description="Globalno sončno obsevanje (W/m2)",
        examples=["161"],
    )
    global_solar_radiation_average_wm2: Optional[int] = Field(
        default=None,
        alias="gSunRadavg",
        description="Povprečno globalno sončno obsevanje v časovnem intervalu (W/m2)",
        examples=["171"],
    )
    diffuse_solar_radiation_wm2: Optional[int] = Field(
        default=None,
        alias="diffSunRad",
        description="Difuzno sončno obsevanje (W/m2)",
        examples=["63"],
    )
    diffuse_solar_radiation_average_wm2: Optional[int] = Field(
        default=None,
        alias="diffSunRadavg",
        description="Povprečno difuzno sončno obsevanje v časovnem intervalu (W/m2)",
        examples=["63"],
    )
    visibility_km: Optional[Union[int | float]] = Field(
        default=None, alias="vis_val", description="Vidnost (km)", examples=[""]
    )
    temperature_at_5cm: Optional[float] = Field(
        default=None,
        alias="t_5_cm",
        description="Temperatura na 5 cm (°C)",
        examples=[""],
    )
    temperature_average_at_5cm: Optional[float] = Field(
        default=None,
        alias="tavg_5_cm",
        description="Povprečna temperatura na 5 cm v časovnem intervalu (°C)",
        examples=[""],
    )
    ground_temperature_at_5cm: Optional[float] = Field(
        default=None,
        alias="tg_5_cm",
        description="Temperatura tal v globini 5 cm (°C)",
        examples=["19.6"],
    )
    ground_temperature_average_at_5cm: Optional[float] = Field(
        default=None,
        alias="tgavg_5_cm",
        description="Povprečna temperatura tal v časovnem intervalu v globini 5 cm (°C)",
        examples=["19.6"],
    )
    ground_temperature_at_10cm: Optional[float] = Field(
        default=None,
        alias="tg_10_cm",
        description="Temperatura tal v globini 10 cm (°C)",
        examples=["18.7"],
    )
    ground_temperature_average_at_10cm: Optional[float] = Field(
        default=None,
        alias="tgavg_10_cm",
        description="Povprečna temperatura tal v časovnem intervalu v globini 10 cm (°C)",
        examples=["18.7"],
    )
    ground_temperature_at_20cm: Optional[float] = Field(
        default=None,
        alias="tg_20_cm",
        description="Temperatura tal v globini 20 cm (°C)",
        examples=["16.8"],
    )
    ground_temperature_average_at_20cm: Optional[float] = Field(
        default=None,
        alias="tgavg_20_cm",
        description="Povprečna temperatura tal v časovnem intervalu v globini 20 cm (°C)",
        examples=["16.8"],
    )
    ground_temperature_at_30cm: Optional[float] = Field(
        default=None,
        alias="tg_30_cm",
        description="Temperatura tal v globini 30 cm (°C)",
        examples=["14.5"],
    )
    ground_temperature_average_at_30cm: Optional[float] = Field(
        default=None,
        alias="tgavg_30_cm",
        description="Povprečna temperatura tal v časovnem intervalu v globini 30 cm (°C)",
        examples=["14.5"],
    )
    ground_temperature_at_50cm: Optional[float] = Field(
        default=None,
        alias="tg_50_cm",
        description="Temperatura tal v globini 50 cm (°C)",
        examples=["13.5"],
    )
    ground_temperature_average_at_50cm: Optional[float] = Field(
        default=None,
        alias="tgavg_50_cm",
        description="Povprečna temperatura tal v časovnem intervalu v globini 50 cm (°C)",
        examples=["13.5"],
    )

    @computed_field
    @property
    def precipitation_rate(self) -> Optional[float]:
        """
        Precipitation is provided as mm in 10 minutes. This converts it to mm/h.
        """
        if not isinstance(self.precipitation_accumulated_mm, float):
            return None
        rate = (self.precipitation_accumulated_mm / 10) * 60
        return round(rate, 2)

    @field_validator(
        "wind_direction_text",
        "wind_direction_icon",
        "wind_direction_average_text",
        "wind_direction_average_icon",
        "wind_direction_max_gust_text",
        "wind_direction_max_gust_icon",
        mode="after",
    )
    @classmethod
    def remap_cardinal(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return WIND_DIRECTION_MAP.get(value, value)


MODEL_MAPPING: dict[str, Type[BaseModel]] = {
    "forecast1h": Forecast1hTimelineEntry,
    "forecast3h": Forecast3hTimelineEntry,
    "forecast6h": Forecast6hTimelineEntry,
    "forecast24h": Forecast24hTimelineEntry,
}


def merge_observation_data(
    timeline_entry: ObservationTimelineEntry, details: ObservationDetails
) -> ObservationDetails:
    """
    Merges data from an ObservationTimelineEntry and an ObservationDetails
    into a new, comprehensive ObservationDetails instance.

    It prioritizes non-None values from the `details` object for shared fields.
    Fields specific to ObservationDetails are included.
    Fields potentially specific to ObservationTimelineEntry (if any existed)
    would be preserved if not overwritten by a non-None value in details.

    Args:
        timeline_entry: The existing, potentially simpler, observation data.
        details: The newly available, more detailed observation data.

    Returns:
        A new ObservationDetails instance containing the merged data.
    """
    # Get dictionaries of the data, excluding None values unless explicitly set
    # Using model_dump() gets all defined fields, including those currently None
    timeline_data = timeline_entry.model_dump(by_alias=False)  # Use python names
    details_data = details.model_dump(by_alias=False)  # Use python names

    # Start with the timeline data as the base
    merged_data = timeline_data.copy()

    # Iterate through the detailed data
    for key, detail_value in details_data.items():
        # Update the merged data if:
        # 1. The detail_value is not None (prioritize non-None details)
        # 2. OR the key doesn't exist in the original timeline_data (it's a new field)
        if detail_value is not None:
            merged_data[key] = detail_value
        # If detail_value is None, we keep the value from timeline_data (which might also be None)
        # If the key is new (only in details) and its value is None, it will be included as None

    # Create the final, merged ObservationDetails object
    # Pydantic will validate the merged data against the ObservationDetails schema
    final_details = ObservationDetails(**merged_data)

    return final_details
