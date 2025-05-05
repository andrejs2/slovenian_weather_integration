import aiohttp
import logging
from typing import Optional, Literal, Type
from pydantic import BaseModel

from .models import (
    ObservationDetails,
    ObservationTimelineEntry,
    merge_observation_data,
    MODEL_MAPPING,
)
from .station_map import OBSERVATION_STATIONS

_LOGGER = logging.getLogger(__name__)

PRIMARY_STATION_BASE_URL = "https://meteo.arso.gov.si/uploads/probase/www/observ/surface/json/sl//recent/observationAms_METEO-{location_id}_history.json"
OFFICIAL_ARSO_API_URL = (
    "https://vreme.arso.gov.si/api/1.0/location/?location={location_id}"
)
LOCATIONS_URL = (
    "https://vreme.arso.gov.si/uploads/probase/www/fproduct/json/sl/locations.json"
)


class ArsoWeather:
    """Client to fetch weather data from ARSO."""

    def __init__(
        self,
        location_name: str,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        location_id = OBSERVATION_STATIONS.get(location_name)

        self.location_name = location_name
        self.location_id = location_id

        if session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        else:
            self._session = session
            self._owns_session = False

        _LOGGER.debug(f"Initialized ArsoWeather for location '{location_name}'")

    async def get_all_locations(self) -> list[str]:
        "Returns list of all locations provided by ARSO"
        locations = await self.fetch_weather_data(api_url=LOCATIONS_URL)
        return [loc["properties"]["title"] for loc in locations["features"]]

    async def get_weather(self) -> dict[str, Type[BaseModel]]:
        """
        Official API data is fetched in all cases since it is always available for all locations, but lacks lots of information.
        If selected location is primary location (containing full current weather data),
        the data is fetched from it, and then merged with the basic observation data from the official API.

        Official API data also contains forecast data, which is also included in the output.
        Final output contains the following keys: "current", "forecast1h", "forecast3h", "forecast6h", "forecast24h"
        Values are lists of Pydantic objects.
        """
        official_api_url = OFFICIAL_ARSO_API_URL.format(location_id=self.location_name)
        official_data = await self.fetch_weather_data(api_url=official_api_url)
        official_data_parsed = await self.parse_official_weather_data(
            official_data,
            target_keys=[
                "observation",
                "forecast1h",
                "forecast3h",
                "forecast6h",
                "forecast24h",
            ],
        )
        # Basic observation data is always available
        if official_data_observation := official_data_parsed.pop("observation"):
            official_data_observation = official_data_observation[0]
        else:
            official_data_observation = {}
        observation = ObservationTimelineEntry.model_validate(official_data_observation)

        if self.location_id:  # Only if specified location is primary location of ARSO
            primary_station_url = PRIMARY_STATION_BASE_URL.format(
                location_id=self.location_id
            )
            primary_station_data = await self.fetch_weather_data(
                api_url=primary_station_url
            )
            primary_station_data_parsed = await self.parse_primary_weather_data(
                primary_station_data
            )
            full_observation = ObservationDetails.model_validate(
                primary_station_data_parsed
            )
            # Merge the basic observation with the full observation
            observation = merge_observation_data(observation, full_observation)

        forecasts = {
            data_type: [MODEL_MAPPING[data_type].model_validate(d) for d in data]
            for data_type, data in official_data_parsed.items()
        }

        return forecasts | {
            "current": [observation]  # is list for consistency with forecast data
        }

    async def fetch_weather_data(self, api_url: str) -> dict:
        """Fetches and returns the current weather data.
        Returns:
            A Pydantic model (WeatherState) containing the current weather data.

        Raises:
            ArsoApiError: If the API request fails.
            ArsoDataError: If the response format is unexpected or data is missing/invalid.
            pydantic.ValidationError: If the data fails Pydantic validation.
        """
        _LOGGER.debug(f"Requesting weather data from {api_url}")

        try:
            async with self._session.get(api_url) as response:
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
                data = await response.json(content_type=None)
                _LOGGER.debug("Successfully received API response.")
                return data
        except aiohttp.ClientResponseError as e:
            _LOGGER.error(f"API request failed: {e.status} {e.message}")
            return {}
        except aiohttp.ClientError as e:
            _LOGGER.error(f"Client error during API request: {e}")
            return {}

    async def parse_primary_weather_data(self, data: dict) -> dict:
        """Parse the primary weather data from the JSON file."""
        try:
            feature = data["features"][0]
            properties = feature["properties"]
            day_data = properties["days"][0]
            return day_data["timeline"][0]

        except (KeyError, IndexError, TypeError) as e:
            _LOGGER.error(f"Failed to extract data from response structure: {e}")
            return {}
        except Exception as e:  # Catch Pydantic validation errors or others
            _LOGGER.error(f"Failed to validate API data: {e}")
            return {}

    async def parse_official_weather_data(
        self,
        data: dict,
        target_keys: list[
            Literal[
                "observation", "forecast1h", "forecast3h", "forecast6h", "forecast24h"
            ]
        ],
    ) -> dict[str, list]:
        try:
            out = {k: [] for k in target_keys}  # create empty response
            for forecast_type, val in data.items():
                if forecast_type not in target_keys:
                    continue
                for days in val["features"][0]["properties"]["days"]:
                    out[forecast_type] += days["timeline"]
                _LOGGER.debug(
                    f"Got {len(out[forecast_type])} forecasts for {forecast_type}"
                )
            return out

        except (KeyError, IndexError, TypeError) as e:
            return out
        except Exception as e:  # Catch Pydantic validation errors or others
            _LOGGER.error(f"Failed to validate API data: {e}")
            return out

    async def close(self):
        """Close the underlying aiohttp session if it was created internally."""
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            _LOGGER.debug("Closed internally managed aiohttp session.")

    async def __aenter__(self):
        """Async context manager enter."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
